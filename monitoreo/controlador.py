from __future__ import annotations

import time
from typing import Callable

from .analizador import AnalizadorDatos
from .config import es_alerta
from .estacion import EstacionAmbiental, crear_estaciones
from .eventos import (
    EventoAlerta,
    EventoCicloFin,
    EventoEstadoEstacion,
    EventoFinSimulacion,
    EventoInicio,
    EventoMedicion,
)
from .modelos import AlertaAmbiental, Medicion, ResultadoEjecucion

# Callback opcional para emitir eventos hacia la GUI. 
# Si es None, el controlador funciona en modo silencioso. 
# Si esta seteado, se emiten eventos en tiempo real. 
# Para la version por procesosel callback debe setearse dentro del proceso hijo 
OnEvento = Callable[[object], None]


# Coordina estaciones, analizador, alertas y medicion de rendimiento
# por default es secuencial
class ControladorMonitoreo:

    MODO: str = "secuencial"

    def __init__(self, num_estaciones: int = 4, num_ciclos: int = 10, intensidad: int = 2000, ventana: int = 10, semilla_base: int = 1234, on_evento: OnEvento | None = None,) -> None:

        if num_estaciones < 1:
            raise ValueError("num_estaciones debe ser >= 1")
        if num_ciclos < 1:
            raise ValueError("num_ciclos debe ser >= 1")
        self.num_estaciones = num_estaciones
        self.num_ciclos = num_ciclos
        self.intensidad = intensidad
        self.ventana = ventana
        self.semilla_base = semilla_base
        self.estaciones: list[EstacionAmbiental] = crear_estaciones(
            num_estaciones, semilla_base=semilla_base
        )
        self.analizador = AnalizadorDatos(intensidad=intensidad, ventana=ventana)
        self.alertas: list[AlertaAmbiental] = []
        self.tiempos_por_ciclo: list[float] = []
        self.on_evento = on_evento

    # secuencial por defecto y se debe sobreescribir en subclases
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
        t0 = time.perf_counter()
        for ciclo in range(self.num_ciclos):
            tc0 = time.perf_counter()
            mediciones: list[Medicion] = []
            for estacion in self.estaciones:
                self._emitir(EventoEstadoEstacion(
                    estacion_id=estacion.id, estado="procesando", ciclo=ciclo
                ))
                meds_estacion = estacion.generar_ciclo(ciclo)
                mediciones.extend(meds_estacion)
                for m in meds_estacion:
                    self._emitir(EventoMedicion(
                        estacion_id=m.estacion_id, zona=m.zona,
                        variable=m.variable, valor=m.valor, ciclo=m.ciclo,
                    ))
                self._emitir(EventoEstadoEstacion(
                    estacion_id=estacion.id, estado="activa", ciclo=ciclo
                ))
            self.analizador.procesar_ciclo(mediciones, ciclo)
            self._evaluar_alertas(mediciones, ciclo)
            tiempo_ciclo = time.perf_counter() - tc0
            self.tiempos_por_ciclo.append(tiempo_ciclo)
            self._emitir(EventoCicloFin(
                ciclo=ciclo,
                tiempo_ciclo=tiempo_ciclo,
                mediciones_ciclo=len(mediciones),
                alertas_ciclo=sum(
                    1 for a in self.alertas if a.ciclo == ciclo
                ),
                indice_zona=dict(self.analizador._riesgo_acum_zona),
            ))
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

    def _emitir(self, evento: object) -> None:
        """Emite un evento al callback si esta configurado."""
        if self.on_evento is not None:
            self.on_evento(evento)

    # utilidades compartidas
    def _evaluar_alertas(self, mediciones: list[Medicion], ciclo: int) -> None:
        for m in mediciones:
            hay, tipo, umbral = es_alerta(m.variable, m.valor)
            if hay:
                severidad = abs(m.valor - umbral) / umbral if umbral else 0.0
                self.alertas.append(
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
                self._emitir(EventoAlerta(
                    estacion_id=m.estacion_id, zona=m.zona,
                    variable=m.variable, valor=m.valor, umbral=umbral,
                    tipo=tipo, severidad=severidad, ciclo=ciclo,
                ))

    # Construye el ResultadoEjecucion estandar a partir del estado actual
    def _construir_resultado(self, tiempo_total: float) -> ResultadoEjecucion:
        resumen = self.analizador.resumen()
        total_mediciones = resumen["total_mediciones"]
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
            tiempos_por_ciclo=list(self.tiempos_por_ciclo),
            total_mediciones=total_mediciones,
            mediciones_por_segundo=mediciones_por_segundo,
            total_alertas=len(self.alertas),
            zona_mayor_riesgo=resumen["zona_mayor_riesgo"],
            indice_ambiental=dict(resumen["indice_ambiental"]),
            estadisticas=dict(resumen["estadisticas"]),
        )
