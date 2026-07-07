# Worker lanzador del job MPI para la GUI (tkinter).
#
# A diferencia de WorkerSimulacion (que corre un controlador dentro del proceso
# de la GUI), el modo MPI necesita `mpiexec`: la GUI no puede ser ella misma un
# rank SPMD. Este worker lanza `mpiexec ... --emitir` como SUBPROCESO y lee su
# stdout fusionado (todos los ranks) linea a linea; cada linea con marcador de
# evento se reconstruye y se publica en la misma queue.Queue que consume la
# ventana, de modo que el feed en vivo reutiliza el mismo bucle de eventos que
# los modos secuencial/hilos/procesos. Las lineas sin marcador (comando,
# warnings de Open MPI, errores de PRTE) se publican como ("log", ...).

from __future__ import annotations

import queue
import signal
import subprocess
import threading

from mpi_monitoreo.eventos_json import json_a_evento


# Construye el argv de `mpiexec` a partir de la config de la GUI. Funcion pura
# (sin efectos) para poder probarla sin lanzar nada. Sin hostfile arma un
# comando local (util para pruebas); con hostfile arma el comando de cluster
# con los flags que ya se usan por consola (--map-by slot, --bind-to none,
# --mca ..._if_include <subred>, -wdir <proyecto>).
def construir_comando(*, n: int, estaciones: int, ciclos: int, intensidad: int, ventana: int, semilla: int, secuencial: bool, salida: str = "resultados", hostfile: str = "", subred: str = "", proyecto: str = "/opt/practica", python_bin: str = "",) -> list[str]:
    py = python_bin or f"{proyecto.rstrip('/')}/.venv/bin/python"
    cmd = ["mpiexec", "-n", str(n)]
    if hostfile:
        cmd += ["-hostfile", hostfile, "--map-by", "slot", "--bind-to", "none",
                "-wdir", proyecto]
        if subred:
            cmd += ["--mca", "btl_tcp_if_include", subred,
                    "--mca", "oob_tcp_if_include", subred]
    cmd += [py, "-m", "mpi_monitoreo.practica_mpi",
            "--estaciones", str(estaciones), "--ciclos", str(ciclos),
            "--intensidad", str(intensidad), "--ventana", str(ventana),
            "--semilla", str(semilla), "--salida", salida, "--emitir"]
    if secuencial:
        cmd.append("--secuencial")
    return cmd


class WorkerMpi(threading.Thread):

    def __init__(self, comando: list[str], cola: queue.Queue) -> None:
        super().__init__(daemon=True)
        self._comando = comando
        self._cola = cola
        self._proc: subprocess.Popen | None = None
        self._detenido = False

    # Aborta el job: SIGINT a mpiexec, que lo propaga a todos los ranks.
    def detener(self) -> None:
        self._detenido = True
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.send_signal(signal.SIGINT)
            except (ProcessLookupError, OSError):
                pass

    def run(self) -> None:
        self._cola.put(("log", "$ " + " ".join(self._comando)))
        try:
            self._proc = subprocess.Popen(
                self._comando,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except (OSError, ValueError) as e:
            self._cola.put(("error", f"No se pudo lanzar mpiexec: {e}"))
            self._cola.put(("finished", None))
            return

        assert self._proc.stdout is not None
        for linea in self._proc.stdout:
            evento = json_a_evento(linea)
            if evento is not None:
                self._cola.put(("evento", evento))
            else:
                texto = linea.rstrip("\n")
                if texto:
                    self._cola.put(("log", texto))

        codigo = self._proc.wait()
        if self._detenido:
            self._cola.put(("detenida", None))
        elif codigo != 0:
            self._cola.put(("error", f"mpiexec termino con codigo {codigo}"))
        self._cola.put(("finished", None))
