# Configuracion central del sistema de monitoreo ambiental de Cuenca

from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class VariableConfig:
    # Parametros de simulacion de una variable ambiental.
    nombre: str
    unidad: str
    media: float
    desviacion: float
    umbral_min: float | None
    umbral_max: float | None
    peso: float

    # Normaliza un valor a un riesgo en [0, ~1.5] respecto a los umbrales
    def riesgo(self, valor: float) -> float:
        """
        0  -> valor muy por debajo del umbral (sin riesgo).
        1  -> valor justo en el umbral.
        >1 -> valor que supera el umbral (genera alerta).
        """
        r_max = valor / self.umbral_max if self.umbral_max else 0.0
        r_min = (self.umbral_min / valor) if (self.umbral_min and valor > 0) else 0.0
        return max(r_max, r_min)


VARIABLES: dict[str, VariableConfig] = {
    "temperatura": VariableConfig("temperatura", "°C", 14.0, 3.5, 2.0, 22.0, 0.15),
    "humedad": VariableConfig("humedad", "%", 72.0, 8.0, 40.0, 92.0, 0.10),
    "ruido": VariableConfig("ruido", "dB", 55.0, 12.0, None, 80.0, 0.20),
    "co2": VariableConfig("co2", "ppm", 420.0, 25.0, None, 470.0, 0.15),
    "pm25": VariableConfig("pm25", "ug/m3", 18.0, 7.0, None, 30.0, 0.25),
    "pm10": VariableConfig("pm10", "ug/m3", 28.0, 10.0, None, 48.0, 0.15),
}

VARIABLES_POR_DEFECTO: tuple[str, ...] = tuple(VARIABLES.keys())

PESO_TOTAL: float = sum(v.peso for v in VARIABLES.values())

ZONAS_CUENCA: tuple[str, ...] = (
    "Centro Historico",
    "San Blas",
    "San Sebastian",
    "El Sagrario",
    "El Vecino",
    "Banos",
    "Monay",
    "Yanuncay",
    "Tomebamba",
    "Los Eucaliptos",
    "Sayausi",
    "Nulti",
)

NOMBRE_ESTACION_PLANTILLA = "Estacion-{zona}"

# Devuelve (hay_alerta, tipo, umbral) para una medicion
def es_alerta(variable: str, valor: float) -> tuple[bool, str, float]:
    cfg = VARIABLES[variable]
    if cfg.umbral_max is not None and valor >= cfg.umbral_max:
        return True, "max", cfg.umbral_max
    if cfg.umbral_min is not None and valor <= cfg.umbral_min:
        return True, "min", cfg.umbral_min
    return False, "", 0.0
