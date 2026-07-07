"""Serializacion de Eventos a lineas JSON para el canal stdout del job MPI.

La GUI lanza `mpiexec ... --emitir` como subproceso y lee su stdout fusionado.
Cada rank imprime sus Eventos como una linea JSON (un solo `print(..., flush)`)
precedida de un marcador `@EVT@`. La GUI busca el marcador en cada linea y
reconstruye el Evento; cualquier otra salida (warnings de Open MPI, PRTE, etc.)
no lleva el marcador y se trata como log, no como evento.

El marcador se busca en CUALQUIER posicion de la linea, para tolerar el prefijo
`[host:rank]` que agrega `mpiexec --tag-output` y el interleaving ocasional de
lineas de ranks concurrentes (una linea corrupta simplemente no parsea y cae al
log, sin romper la GUI).
"""

from __future__ import annotations

import json
from dataclasses import asdict

from monitoreo.eventos import (
    EventoAlerta,
    EventoCicloFin,
    EventoEstadoEstacion,
    EventoFinSimulacion,
    EventoInicio,
    EventoMedicion,
    EventoMetricas,
)

MARCADOR = "@EVT@"

_TIPOS = {
    cls.__name__: cls
    for cls in (
        EventoInicio,
        EventoEstadoEstacion,
        EventoMedicion,
        EventoAlerta,
        EventoCicloFin,
        EventoFinSimulacion,
        EventoMetricas,
    )
}


# Serializa un Evento a una unica linea (sin salto) lista para imprimir.
def evento_a_json(evento: object) -> str:
    datos = asdict(evento)
    datos["_tipo"] = type(evento).__name__
    return MARCADOR + json.dumps(datos, ensure_ascii=False)


# Reconstruye el Evento de una linea de stdout, o None si la linea no es un
# evento (no lleva marcador) o esta corrupta (interleaving, JSON invalido).
def json_a_evento(linea: str) -> object | None:
    pos = linea.find(MARCADOR)
    if pos < 0:
        return None
    try:
        datos = json.loads(linea[pos + len(MARCADOR):])
        cls = _TIPOS[datos.pop("_tipo")]
    except (ValueError, KeyError):
        return None
    # JSON convierte las tuplas (id, nombre, zona) de EventoInicio en listas;
    # las devolvemos a tuplas para conservar la forma original del Evento.
    if cls is EventoInicio and "estaciones" in datos:
        datos["estaciones"] = [tuple(e) for e in datos["estaciones"]]
    try:
        return cls(**datos)
    except TypeError:
        return None
