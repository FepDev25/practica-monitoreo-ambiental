# Worker de simulacion (tkinter)

from __future__ import annotations

import queue
import threading

from monitoreo.controlador import ControladorMonitoreo


# Ejecuta la simulacion en un hilo aparte y publica los Eventos en una cola.
#
# tkinter NO es thread-safe: ningun widget puede tocarse fuera del hilo de la
# GUI. Por eso el worker no toca la interfaz; deja cada Evento en una
# queue.Queue (thread-safe) y la ventana la drena con root.after() desde su
# propio hilo. Sustituye al QThread + pyqtSignal de la version PyQt6, pero
# conserva el mismo desacople: el controlador solo conoce el callback
# on_evento (patron Observer).
class WorkerSimulacion(threading.Thread):

    def __init__(
        self,
        clase_controlador: type[ControladorMonitoreo],
        num_estaciones: int,
        num_ciclos: int,
        intensidad: int,
        ventana: int,
        cola: queue.Queue,
    ) -> None:
        super().__init__(daemon=True)
        self._clase = clase_controlador
        self._num_estaciones = num_estaciones
        self._num_ciclos = num_ciclos
        self._intensidad = intensidad
        self._ventana = ventana
        self._cola = cola
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
        except KeyboardInterrupt:
            self._cola.put(("detenida", None))
        except Exception as e:  # noqa: BLE001
            self._cola.put(("error", f"{type(e).__name__}: {e}"))
        finally:
            self._cola.put(("finished", None))

    # Callback que recibe el controlador. Corre en el hilo del worker.
    def _emitir(self, evento: object) -> None:
        if self._stop.is_set():
            raise KeyboardInterrupt("simulacion detenida por el usuario")
        self._cola.put(("evento", evento))
