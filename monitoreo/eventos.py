# Eventos que viajan desde la simulacion hacia la GUI

from __future__ import annotations

from dataclasses import dataclass, field

@dataclass(frozen=True, slots=True)
class EventoInicio:
    modo: str
    num_estaciones: int
    num_ciclos: int
    intensidad: int
    estaciones: list[tuple[str, str, str]] = field(default_factory=list)

# Cambio de estado de una estacion: 'esperando'|'procesando'|'activa'|'finalizada'
@dataclass(frozen=True, slots=True)
class EventoEstadoEstacion:
    estacion_id: str
    estado: str
    ciclo: int

@dataclass(frozen=True, slots=True)
class EventoMedicion:
    estacion_id: str
    zona: str
    variable: str
    valor: float
    ciclo: int

@dataclass(frozen=True, slots=True)
class EventoAlerta:
    estacion_id: str
    zona: str
    variable: str
    valor: float
    umbral: float
    tipo: str
    severidad: float
    ciclo: int

@dataclass(frozen=True, slots=True)
class EventoCicloFin:
    ciclo: int
    tiempo_ciclo: float
    mediciones_ciclo: int
    alertas_ciclo: int
    indice_zona: dict[str, float] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class EventoFinSimulacion:
    tiempo_total: float
    total_mediciones: int
    total_alertas: int
    mediciones_por_segundo: float
    zona_mayor_riesgo: str | None
    indice_ambiental: dict[str, float] = field(default_factory=dict)

# Tipo union para anotaciones
Evento = (
    EventoInicio
    | EventoEstadoEstacion
    | EventoMedicion
    | EventoAlerta
    | EventoCicloFin
    | EventoFinSimulacion
)
