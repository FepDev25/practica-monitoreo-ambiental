# Worker de simulacion

from __future__ import annotations

import queue
import threading
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from monitoreo.controlador import ControladorMonitoreo
from monitoreo.eventos import (
    EventoAlerta,
    EventoCicloFin,
    EventoEstadoEstacion,
    EventoFinSimulacion,
    EventoInicio,
    EventoMedicion,
)

# Ejecuta la simulacion en un hilo aparte y emite senales Qt
class WorkerSimulacion(QThread):

    # Senales tipadas
    inicio = pyqtSignal(object)
    estado_estacion = pyqtSignal(object)
    medicion = pyqtSignal(object)
    alerta = pyqtSignal(object)
    ciclo_fin = pyqtSignal(object)
    fin_simulacion = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(
        self, clase_controlador: type[ControladorMonitoreo], num_estaciones: int,
        num_ciclos: int, intensidad: int, ventana: int,
        parent: Any = None,) -> None:
        super().__init__(parent)
        self._clase = clase_controlador
        self._num_estaciones = num_estaciones
        self._num_ciclos = num_ciclos
        self._intensidad = intensidad
        self._ventana = ventana
        self._stop = threading.Event()

    def detener(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            controlador = self._clase(
                num_estaciones=self._num_estaciones,
                num_ciclos=self._num_ciclos,
                intensidad=self._intensidad,
                ventana=self._ventana,
                on_evento=self._emitir,
            )
            controlador.ejecutar()
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")

    def _emitir(self, evento: object) -> None:
        if self._stop.is_set():
            raise KeyboardInterrupt("simulacion detenida por el usuario")
        if isinstance(evento, EventoInicio):
            self.inicio.emit(evento)
        elif isinstance(evento, EventoEstadoEstacion):
            self.estado_estacion.emit(evento)
        elif isinstance(evento, EventoMedicion):
            self.medicion.emit(evento)
        elif isinstance(evento, EventoAlerta):
            self.alerta.emit(evento)
        elif isinstance(evento, EventoCicloFin):
            self.ciclo_fin.emit(evento)
        elif isinstance(evento, EventoFinSimulacion):
            self.fin_simulacion.emit(evento)
