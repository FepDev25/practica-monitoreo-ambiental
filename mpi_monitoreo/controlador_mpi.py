"""Controlador MPI (SPMD) del sistema de monitoreo ambiental.

Modelo de ejecucion
-------------------
El mismo programa lo ejecutan `size` procesos MPI. La ciudad (conjunto de
estaciones) se reparte por dominio: cada rank simula su lote de estaciones
con memoria local y, al final, los resultados se consolidan en el rank 0.

Mapa de comunicacion
--------------------
- bcast   (colectiva)      : el rank 0 difunde los parametros de simulacion.
- scatter (colectiva)      : el rank 0 reparte que estaciones le tocan a cada rank.
- isend / recv (p2p)       : cada worker envia (no bloqueante) sus alertas al rank 0.
- gather  (colectiva)      : el rank 0 reune los agregados parciales de cada rank.
- Reduce  (colectiva)      : suma escalares de control (mediciones) sobre buffer numpy.
- Barrier (colectiva)      : acota la region cronometrada (tiempo paralelo Tp).

Carga de CPU
------------
El analisis pesado (suavizado del tensor de riesgo en `AnalizadorDatos`) se
ejecuta dentro de cada rank sobre SUS estaciones, de modo que repartir
estaciones reparte tambien el computo intensivo: ese es el origen del
aceleramiento frente a la version secuencial.
"""

from __future__ import annotations

import numpy as np
from mpi4py import MPI

from monitoreo.analizador import AnalizadorDatos
from monitoreo.config import es_alerta
from monitoreo.estacion import crear_estacion
from monitoreo.modelos import AlertaAmbiental, Medicion, ResultadoEjecucion

from .consolidacion import consolidar, repartir_estaciones

TAG_ALERTAS = 100


class ControladorMPI:
    """Coordina la simulacion distribuida con MPI.

    Todos los ranks construyen el controlador con los mismos parametros (los
    recibe por argv bajo SPMD); aun asi, el rank 0 los difunde por `bcast`
    para evidenciar la comunicacion colectiva exigida por la practica.
    """

    MODO = "mpi"

    def __init__(self, num_estaciones: int = 4, num_ciclos: int = 10, intensidad: int = 2000, ventana: int = 10, semilla_base: int = 1234, comm: MPI.Comm | None = None,) -> None:
        if num_estaciones < 1:
            raise ValueError("num_estaciones debe ser >= 1")
        if num_ciclos < 1:
            raise ValueError("num_ciclos debe ser >= 1")
        self.num_estaciones = num_estaciones
        self.num_ciclos = num_ciclos
        self.intensidad = intensidad
        self.ventana = ventana
        self.semilla_base = semilla_base
        self.comm = comm or MPI.COMM_WORLD
        self.rank = self.comm.Get_rank()
        self.size = self.comm.Get_size()

    def ejecutar(self) -> ResultadoEjecucion | None:
        """Ejecuta la simulacion distribuida.

        Devuelve un `ResultadoEjecucion` en el rank 0 (incluye Tp en
        `tiempo_total`) y `None` en los demas ranks.
        """
        comm, rank, size = self.comm, self.rank, self.size

        # --- bcast (colectiva): el rank 0 difunde los parametros ---
        params = None
        if rank == 0:
            params = {
                "num_estaciones": self.num_estaciones,
                "num_ciclos": self.num_ciclos,
                "intensidad": self.intensidad,
                "ventana": self.ventana,
                "semilla_base": self.semilla_base,
            }
        params = comm.bcast(params, root=0)
        self.num_estaciones = params["num_estaciones"]
        self.num_ciclos = params["num_ciclos"]
        self.intensidad = params["intensidad"]
        self.ventana = params["ventana"]
        self.semilla_base = params["semilla_base"]

        # --- scatter (colectiva): el rank 0 reparte las estaciones ---
        asignacion = (
            repartir_estaciones(self.num_estaciones, size) if rank == 0 else None
        )
        indices_locales: list[int] = comm.scatter(asignacion, root=0)

        # --- region cronometrada (Tp) ---
        comm.Barrier()
        t0 = MPI.Wtime()

        resultado_local = self._simular_local(indices_locales)
        alertas_locales = resultado_local["alertas"]
        parcial_local = resultado_local["parcial"]

        # --- p2p no bloqueante: los workers envian sus alertas al rank 0 ---
        if rank != 0:
            req = comm.isend(alertas_locales, dest=0, tag=TAG_ALERTAS)
            req.wait()
            alertas_globales: list[AlertaAmbiental] = []
        else:
            alertas_globales = list(alertas_locales)
            for origen in range(1, size):
                alertas_globales.extend(comm.recv(source=origen, tag=TAG_ALERTAS))

        # --- gather (colectiva): el rank 0 reune los parciales ---
        parciales = comm.gather(parcial_local, root=0)

        # --- Reduce (colectiva sobre buffer numpy): control de mediciones ---
        local_meds = np.array([parcial_local["total_mediciones"]], dtype=np.int64)
        total_meds = np.zeros(1, dtype=np.int64)
        comm.Reduce(local_meds, total_meds, op=MPI.SUM, root=0)

        # tiempo paralelo: el rank mas lento (Barrier antes de parar el reloj)
        comm.Barrier()
        tp = MPI.Wtime() - t0
        tp_max = comm.reduce(tp, op=MPI.MAX, root=0)

        if rank != 0:
            return None

        return self._consolidar_resultado(
            parciales, alertas_globales, tp_max, int(total_meds[0])
        )

    # Simula localmente el lote de estaciones de este rank durante todos los
    # ciclos: genera mediciones (etiquetadas con el rank), corre el analisis
    # pesado y acumula alertas. Devuelve las alertas y los agregados parciales.
    def _simular_local(self, indices_locales: list[int]) -> dict:
        estaciones = [
            crear_estacion(i, semilla_base=self.semilla_base) for i in indices_locales
        ]
        analizador = AnalizadorDatos(intensidad=self.intensidad, ventana=self.ventana)
        alertas: list[AlertaAmbiental] = []

        for ciclo in range(self.num_ciclos):
            mediciones: list[Medicion] = []
            for estacion in estaciones:
                mediciones.extend(estacion.generar_ciclo(ciclo, rank_mpi=self.rank))
            analizador.procesar_ciclo(mediciones, ciclo)
            alertas.extend(self._evaluar_alertas(mediciones, ciclo))

        return {"alertas": alertas, "parcial": analizador.parciales()}

    # Genera las alertas de un ciclo (misma logica que el controlador base).
    def _evaluar_alertas(self, mediciones: list[Medicion], ciclo: int) -> list[AlertaAmbiental]:
        alertas: list[AlertaAmbiental] = []
        for m in mediciones:
            hay, tipo, umbral = es_alerta(m.variable, m.valor)
            if hay:
                severidad = abs(m.valor - umbral) / umbral if umbral else 0.0
                alertas.append(
                    AlertaAmbiental(
                        estacion_id=m.estacion_id,
                        zona=m.zona,
                        variable=m.variable,
                        valor=m.valor,
                        umbral=umbral,
                        tipo=tipo,
                        severidad=severidad,
                        ciclo=ciclo,
                        tiempo=m.tiempo,
                    )
                )
        return alertas

    # Construye el ResultadoEjecucion final en el rank 0.
    def _consolidar_resultado(self, parciales: list[dict], alertas: list[AlertaAmbiental], tiempo_total: float, total_mediciones_reduce: int,) -> ResultadoEjecucion:
        resumen = consolidar(parciales)
        # total_mediciones llega por dos caminos (gather y Reduce); deben
        # coincidir. Usamos el del Reduce como verificacion cruzada.
        total_mediciones = resumen["total_mediciones"]
        assert total_mediciones == total_mediciones_reduce, (
            "Descuadre entre gather y Reduce en total_mediciones"
        )

        tiempo_promedio_ciclo = (
            tiempo_total / self.num_ciclos if self.num_ciclos else 0.0
        )
        mediciones_por_segundo = (
            total_mediciones / tiempo_total if tiempo_total > 0 else 0.0
        )

        return ResultadoEjecucion(
            modo=self.MODO,
            num_estaciones=self.num_estaciones,
            num_ciclos=self.num_ciclos,
            intensidad=self.intensidad,
            tiempo_total=tiempo_total,
            tiempo_promedio_ciclo=tiempo_promedio_ciclo,
            tiempos_por_ciclo=[],
            total_mediciones=total_mediciones,
            mediciones_por_segundo=mediciones_por_segundo,
            total_alertas=len(alertas),
            zona_mayor_riesgo=resumen["zona_mayor_riesgo"],
            indice_ambiental=dict(resumen["indice_ambiental"]),
            estadisticas=dict(resumen["estadisticas"]),
        )
