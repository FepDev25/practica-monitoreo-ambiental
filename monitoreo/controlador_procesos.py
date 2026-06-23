from __future__ import annotations

import multiprocessing as mp
import queue
import threading
import time
from typing import Any

from .controlador import ControladorMonitoreo
from .eventos import (
    EventoCicloFin,
    EventoEstadoEstacion,
    EventoFinSimulacion,
    EventoInicio,
    EventoMedicion,
)
from .modelos import Medicion, ResultadoEjecucion


def _trabajador_estacion(
    estacion: Any,
    num_ciclos: int,
    evento_inicio: Any,
    evento_detener: Any,
    barrera_inicio_ciclo: Any,
    barrera_fin_ciclo: Any,
    cola_mediciones: Any,
    cola_eventos: Any,
) -> None:
    """Proceso hijo: genera mediciones de una estacion y las envia al controlador."""
    try:
        evento_inicio.wait()

        for ciclo in range(num_ciclos):
            if evento_detener.is_set():
                break

            cola_eventos.put(EventoEstadoEstacion(
                estacion_id=estacion.id,
                estado="esperando",
                ciclo=ciclo,
            ))

            barrera_inicio_ciclo.wait()

            if evento_detener.is_set():
                break

            cola_eventos.put(EventoEstadoEstacion(
                estacion_id=estacion.id,
                estado="procesando",
                ciclo=ciclo,
            ))

            mediciones_estacion = estacion.generar_ciclo(ciclo)
            cola_mediciones.put((ciclo, mediciones_estacion))

            cola_eventos.put(EventoEstadoEstacion(
                estacion_id=estacion.id,
                estado="activa",
                ciclo=ciclo,
            ))

            barrera_fin_ciclo.wait()

    except BaseException as exc:
        cola_eventos.put(("ERROR", estacion.id, repr(exc)))


class ControladorProcesos(ControladorMonitoreo):
    """Controlador concurrente basado en multiprocessing.

    Cada estacion ambiental se ejecuta en un Process independiente.
    La comunicacion entre procesos se realiza mediante Queue.
    La sincronizacion por ciclos se realiza con Barrier y la finalizacion
    coordinada con Event.
    """

    MODO: str = "procesos"

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

        evento_inicio = mp.Event()
        evento_detener = mp.Event()
        barrera_inicio_ciclo = mp.Barrier(self.num_estaciones + 1)
        barrera_fin_ciclo = mp.Barrier(self.num_estaciones + 1)
        cola_mediciones = mp.Queue()
        cola_eventos = mp.Queue()

        procesos: list[mp.Process] = [
            mp.Process(
                target=_trabajador_estacion,
                args=(
                    estacion,
                    self.num_ciclos,
                    evento_inicio,
                    evento_detener,
                    barrera_inicio_ciclo,
                    barrera_fin_ciclo,
                    cola_mediciones,
                    cola_eventos,
                ),
                name=f"Proceso-{estacion.id}",
            )
            for estacion in self.estaciones
        ]

        t0 = time.perf_counter()

        for proceso in procesos:
            proceso.start()

        evento_inicio.set()

        try:
            for ciclo in range(self.num_ciclos):
                tc0 = time.perf_counter()

                self._vaciar_eventos(cola_eventos)

                barrera_inicio_ciclo.wait()
                self._vaciar_eventos(cola_eventos)

                barrera_fin_ciclo.wait()
                self._vaciar_eventos(cola_eventos)

                mediciones_ciclo: list[Medicion] = []

                for _ in range(self.num_estaciones):
                    try:
                        ciclo_recibido, mediciones_estacion = cola_mediciones.get(timeout=30)
                    except queue.Empty as exc:
                        self._vaciar_eventos(cola_eventos)
                        raise RuntimeError(
                            "No se recibieron mediciones desde un proceso."
                        ) from exc

                    if ciclo_recibido != ciclo:
                        raise RuntimeError(
                            f"Se recibio ciclo {ciclo_recibido}, pero se esperaba {ciclo}."
                        )

                    mediciones_ciclo.extend(mediciones_estacion)

                for m in mediciones_ciclo:
                    self._emitir(EventoMedicion(
                        estacion_id=m.estacion_id,
                        zona=m.zona,
                        variable=m.variable,
                        valor=m.valor,
                        ciclo=m.ciclo,
                    ))

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

        except threading.BrokenBarrierError as exc:
            raise RuntimeError("La barrera de procesos se rompio.") from exc

        finally:
            evento_detener.set()

            for proceso in procesos:
                proceso.join(timeout=5)

            for proceso in procesos:
                if proceso.is_alive():
                    proceso.terminate()
                    proceso.join(timeout=2)

            self._vaciar_eventos(cola_eventos)

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
                estacion_id=estacion.id,
                estado="finalizada",
                ciclo=self.num_ciclos,
            ))

        return resultado

    def _vaciar_eventos(self, cola_eventos: Any) -> None:
        """Emite los eventos recibidos desde los procesos hijos."""
        while True:
            try:
                evento = cola_eventos.get_nowait()
            except queue.Empty:
                break

            if isinstance(evento, tuple) and evento and evento[0] == "ERROR":
                _, estacion_id, detalle = evento
                raise RuntimeError(
                    f"Error en el proceso de la estacion {estacion_id}: {detalle}"
                )

            self._emitir(evento)
