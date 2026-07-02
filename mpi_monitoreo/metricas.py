"""Metricas de rendimiento y escritura de resultados (solo rank 0).

Calcula y persiste el aceleramiento S = Ts / Tp y la eficiencia E = S / N.
"""

from __future__ import annotations

import csv
import os

from monitoreo.modelos import ResultadoEjecucion

CAMPOS_CSV = [
    "num_procesos",
    "num_estaciones",
    "num_ciclos",
    "intensidad",
    "total_mediciones",
    "tiempo_secuencial",
    "tiempo_paralelo",
    "speedup",
    "eficiencia",
    "mediciones_por_segundo",
    "total_alertas",
    "zona_mayor_riesgo",
]


# Aceleramiento S = Ts / Tp. Devuelve None si no hay referencia secuencial.
def speedup(ts: float | None, tp: float) -> float | None:
    if ts is None or tp <= 0:
        return None
    return ts / tp


# Eficiencia E = S / N.
def eficiencia(s: float | None, num_procesos: int) -> float | None:
    if s is None or num_procesos <= 0:
        return None
    return s / num_procesos


# Agrega una fila al CSV de resultados (crea cabecera si el archivo no existe).
def escribir_csv(resultado: ResultadoEjecucion, num_procesos: int, ts: float | None, salida: str = "resultados", nombre: str = "mpi.csv",) -> str:
    os.makedirs(salida, exist_ok=True)
    ruta = os.path.join(salida, nombre)
    nuevo = not os.path.exists(ruta)

    s = speedup(ts, resultado.tiempo_total)
    e = eficiencia(s, num_procesos)

    fila = {
        "num_procesos": num_procesos,
        "num_estaciones": resultado.num_estaciones,
        "num_ciclos": resultado.num_ciclos,
        "intensidad": resultado.intensidad,
        "total_mediciones": resultado.total_mediciones,
        "tiempo_secuencial": f"{ts:.6f}" if ts is not None else "",
        "tiempo_paralelo": f"{resultado.tiempo_total:.6f}",
        "speedup": f"{s:.4f}" if s is not None else "",
        "eficiencia": f"{e:.4f}" if e is not None else "",
        "mediciones_por_segundo": f"{resultado.mediciones_por_segundo:.2f}",
        "total_alertas": resultado.total_alertas,
        "zona_mayor_riesgo": resultado.zona_mayor_riesgo or "",
    }

    with open(ruta, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_CSV)
        if nuevo:
            writer.writeheader()
        writer.writerow(fila)

    return ruta
