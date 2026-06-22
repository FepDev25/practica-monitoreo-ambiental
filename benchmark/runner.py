# benchmarking para comparar las versiones del sistema
from __future__ import annotations

import csv
import importlib
import os
import statistics
import time
from dataclasses import asdict, dataclass, field
from typing import Callable

from monitoreo.controlador import ControladorMonitoreo
from monitoreo.entorno import info_entorno
from monitoreo.modelos import ResultadoEjecucion

REGISTRO_CONTROLADORES: list[tuple[str, str, str]] = [
    ("secuencial", "monitoreo.controlador", "ControladorMonitoreo"),
    ("hilos", "monitoreo.controlador_hilos", "ControladorHilos"),
    ("procesos", "monitoreo.controlador_procesos", "ControladorProcesos"),
]

CONFIGURACIONES_POR_DEFECTO: tuple[tuple[int, int], ...] = (
    (4, 10),
    (8, 20),
    (12, 30),
)


@dataclass
class EjecucionRaw:
    configuracion: str
    num_estaciones: int
    num_ciclos: int
    intensidad: int
    modo: str
    repeticion: int
    tiempo_total: float
    tiempo_promedio_ciclo: float
    total_mediciones: int
    mediciones_por_segundo: float
    total_alertas: int
    zona_mayor_riesgo: str | None


@dataclass
class ResumenConfig:
    configuracion: str
    num_estaciones: int
    num_ciclos: int
    intensidad: int
    Ts: float | None = None
    Tthread: float | None = None
    Tprocess: float | None = None
    Sthread: float | None = None
    Sprocess: float | None = None
    mediciones_seq: int = 0
    alertas_seq: int = 0


def descubrir_controladores() -> dict[str, Callable[..., ControladorMonitoreo]]:
    """Importa los controladores disponibles. Devuelve {modo: clase}."""
    disponibles: dict[str, Callable[..., ControladorMonitoreo]] = {}
    for modo, modulo, clase in REGISTRO_CONTROLADORES:
        try:
            mod = importlib.import_module(modulo)
            disponibles[modo] = getattr(mod, clase)
        except (ImportError, AttributeError):
            continue
    return disponibles

# Instancia un controlador nuevo y ejecuta una simulacion completa
def ejecutar_una_vez(clase: Callable[..., ControladorMonitoreo], num_estaciones: int, num_ciclos: int,
    intensidad: int, ventana: int,) -> ResultadoEjecucion:
    
    controlador = clase(
        num_estaciones=num_estaciones,
        num_ciclos=num_ciclos,
        intensidad=intensidad,
        ventana=ventana,
    )
    return controlador.ejecutar()

# Ejecuta el benchmark completo
# Devuelve (ejecuciones_crudas, resumenes_por_config, info_entorno)
def correr_benchmark(configuraciones: tuple[tuple[int, int], ...] = CONFIGURACIONES_POR_DEFECTO,
    repeticiones: int = 3, intensidad: int = 2000, ventana: int = 10,
    modos_permitidos: list[str] | None = None, progreso: Callable[[str], None] | None = None,
) -> tuple[list[EjecucionRaw], list[ResumenConfig], dict]:
    log = progreso or (lambda _: None)
    disponibles = descubrir_controladores()
    if modos_permitidos is not None:
        disponibles = {
            m: c for m, c in disponibles.items() if m in modos_permitidos
        }
    if not disponibles:
        raise RuntimeError("No hay controladores disponibles para ejecutar.")

    log(f"Controladores disponibles: {', '.join(disponibles.keys())}")

    ejecuciones: list[EjecucionRaw] = []
    por_config_modo: dict[tuple[str, str], list[float]] = {}
    metadatos_config: dict[str, tuple[int, int, int]] = {}

    for num_estaciones, num_ciclos in configuraciones:
        etiqueta = f"{num_estaciones}est_{num_ciclos}cic"
        metadatos_config[etiqueta] = (num_estaciones, num_ciclos, intensidad)
        log(f"== Configuracion {etiqueta} (intensidad={intensidad}) ==")
        for modo, clase in disponibles.items():
            for rep in range(1, repeticiones + 1):
                t0 = time.perf_counter()
                resultado = ejecutar_una_vez(
                    clase, num_estaciones, num_ciclos, intensidad, ventana
                )
                wall = time.perf_counter() - t0
                log(
                    f"  {modo:>10} rep {rep}/{repeticiones}: "
                    f"{wall:.3f}s ({resultado.total_mediciones} med, "
                    f"{resultado.total_alertas} alertas)"
                )
                ejecuciones.append(
                    EjecucionRaw(
                        configuracion=etiqueta,
                        num_estaciones=num_estaciones,
                        num_ciclos=num_ciclos,
                        intensidad=intensidad,
                        modo=modo,
                        repeticion=rep,
                        tiempo_total=resultado.tiempo_total,
                        tiempo_promedio_ciclo=resultado.tiempo_promedio_ciclo,
                        total_mediciones=resultado.total_mediciones,
                        mediciones_por_segundo=resultado.mediciones_por_segundo,
                        total_alertas=resultado.total_alertas,
                        zona_mayor_riesgo=resultado.zona_mayor_riesgo,
                    )
                )
                por_config_modo.setdefault((etiqueta, modo), []).append(
                    resultado.tiempo_total
                )

    resumenes = _construir_resumenes(
        por_config_modo, metadatos_config, ejecuciones
    )
    return ejecuciones, resumenes, info_entorno()

def _construir_resumenes(por_config_modo: dict[tuple[str, str], list[float]],
    metadatos: dict[str, tuple[int, int, int]],ejecuciones: list[EjecucionRaw],
) -> list[ResumenConfig]:
    resumenes: list[ResumenConfig] = []
    for etiqueta, (num_estaciones, num_ciclos, intensidad) in metadatos.items():
        Ts = _promedio(por_config_modo.get((etiqueta, "secuencial")))
        Tthread = _promedio(por_config_modo.get((etiqueta, "hilos")))
        Tprocess = _promedio(por_config_modo.get((etiqueta, "procesos")))
        seq_ref = next(
            (e for e in ejecuciones
             if e.configuracion == etiqueta and e.modo == "secuencial"),
            None,
        )
        resumenes.append(
            ResumenConfig(
                configuracion=etiqueta,
                num_estaciones=num_estaciones,
                num_ciclos=num_ciclos,
                intensidad=intensidad,
                Ts=Ts,
                Tthread=Tthread,
                Tprocess=Tprocess,
                Sthread=(Ts / Tthread) if (Ts and Tthread) else None,
                Sprocess=(Ts / Tprocess) if (Ts and Tprocess) else None,
                mediciones_seq=seq_ref.total_mediciones if seq_ref else 0,
                alertas_seq=seq_ref.total_alertas if seq_ref else 0,
            )
        )
    return resumenes


def _promedio(valores: list[float] | None) -> float | None:
    if not valores:
        return None
    return statistics.fmean(valores)

# Persiste ejecuciones crudas, resumen y entorno en CSV
# Devuelve (path_crudo, path_resumen, path_entorno)
def guardar_csv(ejecuciones: list[EjecucionRaw], resumenes: list[ResumenConfig],
    entorno: dict, directorio: str = "resultados",
) -> tuple[str, str, str]:
    os.makedirs(directorio, exist_ok=True)
    path_crudo = os.path.join(directorio, "ejecuciones.csv")
    path_resumen = os.path.join(directorio, "resumen.csv")
    path_entorno = os.path.join(directorio, "entorno.csv")

    with open(path_crudo, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "configuracion", "num_estaciones", "num_ciclos", "intensidad",
            "modo", "repeticion", "tiempo_total", "tiempo_promedio_ciclo",
            "total_mediciones", "mediciones_por_segundo", "total_alertas",
            "zona_mayor_riesgo",
        ])
        for e in ejecuciones:
            w.writerow([
                e.configuracion, e.num_estaciones, e.num_ciclos, e.intensidad,
                e.modo, e.repeticion, f"{e.tiempo_total:.6f}",
                f"{e.tiempo_promedio_ciclo:.6f}", e.total_mediciones,
                f"{e.mediciones_por_segundo:.2f}", e.total_alertas,
                e.zona_mayor_riesgo or "",
            ])

    with open(path_resumen, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "configuracion", "num_estaciones", "num_ciclos", "intensidad",
            "Ts", "Tthread", "Tprocess", "Sthread", "Sprocess",
            "mediciones_seq", "alertas_seq",
        ])
        for r in resumenes:
            w.writerow([
                r.configuracion, r.num_estaciones, r.num_ciclos, r.intensidad,
                _fmt(r.Ts), _fmt(r.Tthread), _fmt(r.Tprocess),
                _fmt(r.Sthread), _fmt(r.Sprocess),
                r.mediciones_seq, r.alertas_seq,
            ])

    with open(path_entorno, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["clave", "valor"])
        for clave, valor in entorno.items():
            w.writerow([clave, valor])

    return path_crudo, path_resumen, path_entorno


def _fmt(x: float | None) -> str:
    return "" if x is None else f"{x:.6f}"

# Devuelve una tabla en texto para imprimir en consola
def tabla_resumen(resumenes: list[ResumenConfig]) -> str:
    if not resumenes:
        return "(sin resumen)"
    cab = (
        f"{'config':<16} {'Ts':>9} {'Tthread':>9} {'Tprocess':>9} "
        f"{'Sthread':>7} {'Sprocess':>8} {'med':>7} {'alert':>6}"
    )
    lineas = [cab, "-" * len(cab)]
    for r in resumenes:
        lineas.append(
            f"{r.configuracion:<16} {_fmt(r.Ts):>9} {_fmt(r.Tthread):>9} "
            f"{_fmt(r.Tprocess):>9} {_fmt(r.Sthread):>7} "
            f"{_fmt(r.Sprocess):>8} {r.mediciones_seq:>7} "
            f"{r.alertas_seq:>6}"
        )
    return "\n".join(lineas)
