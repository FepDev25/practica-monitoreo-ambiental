# Modelos de datos del sistema de monitoreo

from __future__ import annotations

from dataclasses import dataclass, field

# Lectura generada por una estacion ambiental
@dataclass(frozen=True, slots=True)
class Medicion:
    estacion_id: str
    estacion_nombre: str
    zona: str
    variable: str
    valor: float
    ciclo: int
    tiempo: float

    def __str__(self) -> str:
        return (
            f"[ciclo {self.ciclo}] {self.estacion_nombre} ({self.zona}) "
            f"{self.variable}={self.valor:.2f}"
        )

# Alerta generada cuando una variable supera un umbral
@dataclass(frozen=True, slots=True)
class AlertaAmbiental:
    estacion_id: str
    zona: str
    variable: str
    valor: float
    umbral: float
    tipo: str
    severidad: float
    ciclo: int
    tiempo: float

    def __str__(self) -> str:
        return (
            f"ALERTA {self.variable} ({self.tipo}) en {self.zona}: "
            f"{self.valor:.2f} >= umbral {self.umbral:.2f} "
            f"[ciclo {self.ciclo}, sev {self.severidad:.2f}]"
        )

# Estadisticas agregadas de una variable a lo largo de la simulacion
@dataclass(slots=True)
class EstadisticasVariable:
    variable: str
    promedio: float = 0.0
    maximo: float = 0.0
    minimo: float = 0.0
    desviacion: float = 0.0
    total_mediciones: int = 0

# Resultado de ejecucion del controlador
@dataclass(slots=True)
class ResultadoEjecucion:
    modo: str
    num_estaciones: int
    num_ciclos: int
    intensidad: int
    tiempo_total: float
    tiempo_promedio_ciclo: float
    tiempos_por_ciclo: list[float] = field(default_factory=list)
    total_mediciones: int = 0
    mediciones_por_segundo: float = 0.0
    total_alertas: int = 0
    zona_mayor_riesgo: str | None = None
    indice_ambiental: dict[str, float] = field(default_factory=dict)
    estadisticas: dict[str, EstadisticasVariable] = field(default_factory=dict)
