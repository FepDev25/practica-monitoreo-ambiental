"""Consolidacion de los agregados parciales de cada rank MPI.

Cada rank corre su propio `AnalizadorDatos` sobre su lote de estaciones y
expone agregados crudos con `AnalizadorDatos.parciales()`. El rank 0 reune
todos esos parciales (via `comm.gather`) y los combina aqui.

La combinacion es asociativa y reproduce EXACTAMENTE el resultado de la
version secuencial (mismas semillas -> mismos numeros), independientemente
de como se hayan repartido las estaciones entre procesos. Esto se valida
comparando una corrida MPI con N=1 contra la version secuencial.

Esta logica es Python puro (sin mpi4py) para poder probarla sin lanzar MPI.
"""

from __future__ import annotations

from monitoreo.modelos import EstadisticasVariable


# Reparte los indices globales de estacion [0, num_estaciones) entre `size`
# procesos en round-robin. Cada rank r recibe los indices r, r+size, ...
# Round-robin (en vez de bloques contiguos) reparte las zonas entre ranks y
# equilibra la carga cuando num_estaciones no es multiplo de size.
def repartir_estaciones(num_estaciones: int, size: int) -> list[list[int]]:
    asignacion: list[list[int]] = [[] for _ in range(size)]
    for i in range(num_estaciones):
        asignacion[i % size].append(i)
    return asignacion


# Combina los parciales de todos los ranks (lista de dicts de
# AnalizadorDatos.parciales()) en un resumen con la misma forma que
# AnalizadorDatos.resumen(): total_mediciones, estadisticas por variable,
# indice ambiental por zona y zona de mayor riesgo.
def consolidar(parciales: list[dict]) -> dict:
    total_mediciones = 0
    # por variable acumulamos (n, suma, suma_cuadrados, maximo, minimo)
    acum_var: dict[str, list[float]] = {}
    acum_zona: dict[str, float] = {}
    num_ciclos = 0

    for parcial in parciales:
        total_mediciones += parcial["total_mediciones"]
        num_ciclos = max(num_ciclos, parcial["num_ciclos"])

        for variable, (n, suma, sumsq, mx, mn) in parcial["por_variable"].items():
            if variable not in acum_var:
                acum_var[variable] = [n, suma, sumsq, mx, mn]
            else:
                a = acum_var[variable]
                a[0] += n
                a[1] += suma
                a[2] += sumsq
                a[3] = mx if mx > a[3] else a[3]
                a[4] = mn if mn < a[4] else a[4]

        for zona, suma in parcial["acum_zona"].items():
            acum_zona[zona] = acum_zona.get(zona, 0.0) + suma

    estadisticas: dict[str, EstadisticasVariable] = {}
    for variable, (n, suma, sumsq, mx, mn) in acum_var.items():
        if n == 0:
            estadisticas[variable] = EstadisticasVariable(variable=variable)
            continue
        promedio = suma / n
        # var = E[x^2] - E[x]^2 ; identico a la formula del analizador secuencial
        varianza = sumsq / n - promedio * promedio
        desviacion = varianza ** 0.5 if varianza > 0 else 0.0
        estadisticas[variable] = EstadisticasVariable(
            variable=variable,
            promedio=promedio,
            maximo=mx,
            minimo=mn,
            desviacion=desviacion,
            total_mediciones=n,
        )

    # Indice ambiental por zona = riesgo acumulado / numero de ciclos.
    # Sumar acum entre ranks y dividir una sola vez por num_ciclos reproduce
    # el promedio por ciclo que calcula la version secuencial.
    indice_zona: dict[str, float] = {}
    if num_ciclos:
        for zona, suma in acum_zona.items():
            indice_zona[zona] = suma / num_ciclos

    zona_mayor_riesgo: str | None = None
    if indice_zona:
        zona_mayor_riesgo = max(indice_zona, key=indice_zona.get)

    return {
        "total_mediciones": total_mediciones,
        "estadisticas": estadisticas,
        "indice_ambiental": indice_zona,
        "zona_mayor_riesgo": zona_mayor_riesgo,
    }
