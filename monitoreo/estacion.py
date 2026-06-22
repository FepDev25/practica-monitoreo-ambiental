from __future__ import annotations

import random
import time

from .config import NOMBRE_ESTACION_PLANTILLA, VARIABLES, VARIABLES_POR_DEFECTO, ZONAS_CUENCA
from .modelos import Medicion

# Representa una estacion de monitoreo ubicada en una zona de Cuenca
# Genera mediciones simuladas
class EstacionAmbiental:
    def __init__(self, estacion_id: str, zona: str, variables: tuple[str, ...] = VARIABLES_POR_DEFECTO, semilla: int = 0,) -> None:
        self.id = estacion_id
        self.nombre = NOMBRE_ESTACION_PLANTILLA.format(zona=zona)
        self.zona = zona
        self.variables = tuple(variables)
        self._rng = random.Random(semilla)
        self.contador_mediciones = 0

    # Genera una medicion simulada para una variable dada
    def generar_medicion(self, variable: str, ciclo: int) -> Medicion:
        cfg = VARIABLES[variable]
        valor = self._rng.gauss(cfg.media, cfg.desviacion)
        self.contador_mediciones += 1
        return Medicion(
            estacion_id=self.id,
            estacion_nombre=self.nombre,
            zona=self.zona,
            variable=variable,
            valor=valor,
            ciclo=ciclo,
            tiempo=time.time(),
        )

    # Genera una medicion por cada variable de la estacion en un ciclo
    def generar_ciclo(self, ciclo: int) -> list[Medicion]:
        return [self.generar_medicion(v, ciclo) for v in self.variables]

    def __repr__(self) -> str:
        return (
            f"EstacionAmbiental(id={self.id!r}, zona={self.zona!r}, "
            f"variables={self.variables})"
        )

# Crea num_estaciones estaciones distribuidas ciclicamente entre zonas
def crear_estaciones(num_estaciones: int, variables: tuple[str, ...] = VARIABLES_POR_DEFECTO, semilla_base: int = 1234, ) -> list[EstacionAmbiental]:
    estaciones: list[EstacionAmbiental] = []
    for i in range(num_estaciones):
        zona = ZONAS_CUENCA[i % len(ZONAS_CUENCA)]
        estaciones.append(
            EstacionAmbiental(
                estacion_id=f"EST-{i+1:02d}",
                zona=zona,
                variables=variables,
                semilla=semilla_base + i,
            )
        )
    return estaciones
