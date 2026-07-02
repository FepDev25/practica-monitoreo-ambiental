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

    # Genera una medicion simulada para una variable dada.
    # rank_mpi etiqueta el proceso MPI que la genero (-1 = sin MPI).
    def generar_medicion(self, variable: str, ciclo: int, rank_mpi: int = -1) -> Medicion:
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
            rank_mpi=rank_mpi,
        )

    # Genera una medicion por cada variable de la estacion en un ciclo
    def generar_ciclo(self, ciclo: int, rank_mpi: int = -1) -> list[Medicion]:
        return [self.generar_medicion(v, ciclo, rank_mpi) for v in self.variables]

    def __repr__(self) -> str:
        return (
            f"EstacionAmbiental(id={self.id!r}, zona={self.zona!r}, "
            f"variables={self.variables})"
        )

# Crea la estacion correspondiente a un indice global (0-based).
# Centraliza el mapeo indice -> id, zona y semilla, para que cualquier
# proceso (incluido un rank MPI con solo su lote) construya exactamente la
# misma estacion que tendria la version secuencial en esa posicion.
def crear_estacion(indice: int, variables: tuple[str, ...] = VARIABLES_POR_DEFECTO, semilla_base: int = 1234, ) -> EstacionAmbiental:
    return EstacionAmbiental(
        estacion_id=f"EST-{indice+1:02d}",
        zona=ZONAS_CUENCA[indice % len(ZONAS_CUENCA)],
        variables=variables,
        semilla=semilla_base + indice,
    )


# Crea num_estaciones estaciones distribuidas ciclicamente entre zonas
def crear_estaciones(num_estaciones: int, variables: tuple[str, ...] = VARIABLES_POR_DEFECTO, semilla_base: int = 1234, ) -> list[EstacionAmbiental]:
    return [
        crear_estacion(i, variables, semilla_base) for i in range(num_estaciones)
    ]
