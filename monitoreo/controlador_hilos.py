from __future__ import annotations

import os
import threading
import time
from multiprocessing.dummy import Pool as ThreadPool

from .controlador import ControladorMonitoreo
from .eventos import (
    EventoCicloFin,
    EventoEstadoEstacion,
    EventoFinSimulacion,
    EventoInicio,
    EventoMedicion,
)
from .modelos import Medicion, ResultadoEjecucion


class ControladorHilos(ControladorMonitoreo):
    """Controlador concurrente basado en threading.

    Cada estacion ambiental se ejecuta en un Thread propio. Los hilos
    comparten un buffer de mediciones protegido con Lock. Dos Barrier
    sincronizan el inicio y el fin de cada ciclo, de forma que el
    controlador solo analiza cuando todas las estaciones terminaron.

    El analisis pesado (suavizado del tensor de riesgo) se reparte entre un
    ThreadPool, igual que la version de procesos usa un Pool. Bajo el GIL
    (CPython estandar) esto NO acelera, porque solo un hilo ejecuta bytecode
    Python a la vez; en una build free-threading (sin GIL) el mismo codigo
    si aprovecha varios nucleos. Sirve para evidenciar el impacto del GIL.
    """

    MODO: str = "hilos"

    def ejecutar(self) -> ResultadoEjecucion:
        self.alertas.clear()
        self.tiempos_por_ciclo.clear()

        self._emitir(EventoInicio(
            modo=self.MODO,
            num_estaciones=self.num_estaciones,
            num_ciclos=self.num_ciclos,
            intensidad=self.intensidad,
            estaciones=[(e.id, e.nombre, e.zona) for e in self.estaciones],
        ))

        # ThreadPool para repartir el suavizado entre hilos
        n_analisis = min(
            os.cpu_count() or 2,
            self.num_estaciones * len(self.estaciones[0].variables),
        )
        n_analisis = max(2, n_analisis)
        pool_analisis = ThreadPool(processes=n_analisis)
        self.analizador.configurar_paralelismo(pool_analisis.map, n_analisis)

        buffer_mediciones: list[Medicion] = []
        lock_buffer = threading.Lock()
        evento_inicio = threading.Event()
        evento_detener = threading.Event()
        barrera_inicio_ciclo = threading.Barrier(self.num_estaciones + 1)
        barrera_fin_ciclo = threading.Barrier(self.num_estaciones + 1)
        errores: list[BaseException] = []
        lock_errores = threading.Lock()

        def registrar_error(exc: BaseException) -> None:
            with lock_errores:
                errores.append(exc)
            evento_detener.set()
            try:
                barrera_inicio_ciclo.abort()
            except threading.BrokenBarrierError:
                pass
            try:
                barrera_fin_ciclo.abort()
            except threading.BrokenBarrierError:
                pass

        def ejecutar_estacion(estacion) -> None:
            try:
                evento_inicio.wait()
                for ciclo in range(self.num_ciclos):
                    if evento_detener.is_set():
                        break

                    self._emitir(EventoEstadoEstacion(
                        estacion_id=estacion.id, estado="esperando", ciclo=ciclo
                    ))
                    barrera_inicio_ciclo.wait()

                    if evento_detener.is_set():
                        break

                    self._emitir(EventoEstadoEstacion(
                        estacion_id=estacion.id, estado="procesando", ciclo=ciclo
                    ))
                    mediciones_estacion = estacion.generar_ciclo(ciclo)

                    with lock_buffer:
                        buffer_mediciones.extend(mediciones_estacion)

                    for m in mediciones_estacion:
                        self._emitir(EventoMedicion(
                            estacion_id=m.estacion_id,
                            zona=m.zona,
                            variable=m.variable,
                            valor=m.valor,
                            ciclo=m.ciclo,
                        ))

                    self._emitir(EventoEstadoEstacion(
                        estacion_id=estacion.id, estado="activa", ciclo=ciclo
                    ))
                    barrera_fin_ciclo.wait()
            except threading.BrokenBarrierError:
                return
            except BaseException as exc:
                registrar_error(exc)

        hilos = [
            threading.Thread(
                target=ejecutar_estacion,
                args=(estacion,),
                name=f"Hilo-{estacion.id}",
            )
            for estacion in self.estaciones
        ]

        t0 = time.perf_counter()
        for hilo in hilos:
            hilo.start()
        evento_inicio.set()

        try:
            for ciclo in range(self.num_ciclos):
                if errores:
                    break

                tc0 = time.perf_counter()
                barrera_inicio_ciclo.wait()
                barrera_fin_ciclo.wait()

                with lock_buffer:
                    mediciones_ciclo = [m for m in buffer_mediciones if m.ciclo == ciclo]
                    buffer_mediciones[:] = [m for m in buffer_mediciones if m.ciclo != ciclo]

                self.analizador.procesar_ciclo(mediciones_ciclo, ciclo)
                self._evaluar_alertas(mediciones_ciclo, ciclo)

                tiempo_ciclo = time.perf_counter() - tc0
                self.tiempos_por_ciclo.append(tiempo_ciclo)
                self._emitir(EventoCicloFin(
                    ciclo=ciclo,
                    tiempo_ciclo=tiempo_ciclo,
                    mediciones_ciclo=len(mediciones_ciclo),
                    alertas_ciclo=sum(1 for a in self.alertas if a.ciclo == ciclo),
                    indice_zona=dict(self.analizador._riesgo_acum_zona),
                ))
        except threading.BrokenBarrierError:
            pass
        finally:
            evento_detener.set()
            for hilo in hilos:
                hilo.join()
            pool_analisis.close()
            pool_analisis.join()
            self.analizador.configurar_paralelismo(None, 1)

        if errores:
            raise errores[0]

        tiempo_total = time.perf_counter() - t0
        resultado = self._construir_resultado(tiempo_total)

        self._emitir(EventoFinSimulacion(
            tiempo_total=resultado.tiempo_total,
            total_mediciones=resultado.total_mediciones,
            total_alertas=resultado.total_alertas,
            mediciones_por_segundo=resultado.mediciones_por_segundo,
            zona_mayor_riesgo=resultado.zona_mayor_riesgo,
            indice_ambiental=dict(resultado.indice_ambiental),
        ))
        for estacion in self.estaciones:
            self._emitir(EventoEstadoEstacion(
                estacion_id=estacion.id, estado="finalizada", ciclo=self.num_ciclos
            ))
        return resultado
