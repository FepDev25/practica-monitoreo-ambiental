from __future__ import annotations

from collections import deque
from dataclasses import asdict
from typing import Callable

from .config import VARIABLES, es_alerta
from .modelos import EstadisticasVariable, Medicion

class AnalizadorDatos:
    def __init__(self, intensidad: int = 2000, ventana: int = 10) -> None:
        if intensidad < 1:
            raise ValueError("intensidad debe ser >= 1")
        if ventana < 1:
            raise ValueError("ventana debe ser >= 1")
        self.intensidad = intensidad
        self.ventana = ventana
        # Mapper inyectable para repartir el suavizado (p.ej. Pool.map).
        # Si es None, el suavizado se hace secuencialmente en este proceso.
        self._mapper: Callable[[Callable, list], list] | None = None
        self._n_particiones = 1
        self._series: dict[tuple[str, str], deque[float]] = {}
        self._riesgo_acum_zona: dict[str, float] = {}
        self._riesgo_cuenta_zona: dict[str, int] = {}
        self._todas: list[Medicion] = []
        self._ciclos_procesados = 0

    # secuencial, acumula las mediciones del ciclo y ejecuta el analisis
    def procesar_ciclo(self, mediciones: list[Medicion], ciclo: int) -> dict:
        for m in mediciones:
            clave = (m.estacion_id, m.variable)
            serie = self._series.get(clave)
            if serie is None:
                serie = deque(maxlen=self.ventana)
                self._series[clave] = serie
            serie.append(m.valor)
        self._todas.extend(mediciones)
        self._ciclos_procesados += 1

        indice_zona = self._indice_ambiental_compuesto(mediciones)
        for zona, valor in indice_zona.items():
            self._riesgo_acum_zona[zona] = self._riesgo_acum_zona.get(zona, 0.0) + valor
            self._riesgo_cuenta_zona[zona] = self._riesgo_cuenta_zona.get(zona, 0) + 1

        media_movil = self._medias_moviles()
        return {
            "ciclo": ciclo,
            "total_mediciones": len(mediciones),
            "indice_zona": indice_zona,
            "media_movil": media_movil,
        }

    # Media movil por estacion, variable sobre la ventana actual
    def _medias_moviles(self) -> dict[tuple[str, str], float]:
        resultado: dict[tuple[str, str], float] = {}
        for clave, serie in self._series.items():
            n = len(serie)
            if n == 0:
                continue
            suma = 0.0
            for v in serie:
                suma += v
            resultado[clave] = suma / n
        return resultado

    # Calcula el indice ambiental compuesto por zona con suavizado pesado
    def _indice_ambiental_compuesto(self, mediciones: list[Medicion]) -> dict[str, float]:
        series = list(self._series.items())
        if not series:
            return {}

        estacion_zona: dict[str, str] = {}
        for m in mediciones:
            estacion_zona.setdefault(m.estacion_id, m.zona)

        num_series = len(series)
        longitud = self.ventana

        # Cada serie es una fila independiente del tensor (forward-fill hasta
        # completar la ventana). El suavizado de una fila no depende de las
        # demas, por eso se puede repartir entre procesos sin cambiar el
        # resultado.
        filas: list[list[float]] = []
        for clave, serie in series:
            variable = clave[1]
            cfg = VARIABLES[variable]
            valores = list(serie)
            fila = [0.0] * longitud
            for j in range(longitud):
                if j < len(valores):
                    fila[j] = cfg.riesgo(valores[j])
                elif j > 0:
                    fila[j] = fila[j - 1]
                else:
                    fila[j] = 0.0
            filas.append(fila)

        filas = self._suavizar(filas)

        riesgo_por_estacion: dict[str, float] = {}
        cuenta_por_estacion: dict[str, int] = {}
        for i, (clave, _) in enumerate(series):
            estacion_id = clave[0]
            actual = filas[i][longitud - 1]
            riesgo_por_estacion[estacion_id] = (
                riesgo_por_estacion.get(estacion_id, 0.0) + actual
            )
            cuenta_por_estacion[estacion_id] = (
                cuenta_por_estacion.get(estacion_id, 0) + 1
            )

        indice_zona: dict[str, float] = {}
        suma_global = 0.0
        cuenta_global = 0
        for estacion_id, suma in riesgo_por_estacion.items():
            zona = estacion_zona.get(estacion_id, "desconocida")
            n = cuenta_por_estacion[estacion_id]
            indice_zona[zona] = indice_zona.get(zona, 0.0) + suma / n
            suma_global += suma
            cuenta_global += n

        indice_global = suma_global / cuenta_global if cuenta_global else 0.0
        indice_zona["_global"] = indice_global
        return indice_zona

    # Configura un mapper paralelo (p.ej. Pool.map) para repartir el suavizado
    # entre varios procesos. n_particiones define en cuantos bloques se divide
    # el trabajo. Llamar con mapper=None vuelve al modo secuencial.
    def configurar_paralelismo(self, mapper: Callable[[Callable, list], list] | None, n_particiones: int,) -> None:
        self._mapper = mapper
        self._n_particiones = max(1, n_particiones)

    # Aplica el suavizado de 3 puntos (carga de CPU) a cada fila. Si hay un
    # mapper configurado, reparte las filas en bloques para procesarlas en
    # paralelo; el resultado es identico al secuencial porque cada fila se
    # suaviza de forma independiente.
    def _suavizar(self, filas: list[list[float]]) -> list[list[float]]:
        if not filas:
            return filas
        if self._mapper is None or self._n_particiones <= 1 or len(filas) < 2:
            return _suavizar_filas(filas, self.intensidad)
        bloques = _particionar(filas, self._n_particiones)
        resultados = self._mapper(
            _suavizar_chunk, [(bloque, self.intensidad) for bloque in bloques]
        )
        return [fila for sub in resultados for fila in sub]

    # uso por procesos sin estado para Pool
    def analizar_bloque(self,mediciones: list[Medicion],intensidad: int | None = None,) -> dict:
        n = len(mediciones)
        if n == 0:
            return {
                "total_mediciones": 0,
                "estadisticas": {},
                "indice_compuesto": 0.0,
                "indice_zona": {},
                "alertas_bloque": 0,
            }
        intens = intensidad if intensidad is not None else self.intensidad

        por_variable: dict[str, list[float]] = {}
        for m in mediciones:
            por_variable.setdefault(m.variable, []).append(m.valor)

        estadisticas: dict[str, EstadisticasVariable] = {}
        for variable, valores in por_variable.items():
            estadisticas[variable] = _estadisticas_variable(variable, valores)

        riesgos = [VARIABLES[m.variable].riesgo(m.valor) for m in mediciones]
        riesgos_suavizados = self._suavizar_plano(riesgos, intens)

        por_zona: dict[str, list[float]] = {}
        for m, r in zip(mediciones, riesgos_suavizados):
            por_zona.setdefault(m.zona, []).append(r)

        indice_zona = {
            zona: sum(vals) / len(vals) for zona, vals in por_zona.items()
        }
        indice_compuesto = sum(riesgos_suavizados) / n

        alertas = 0
        for m in mediciones:
            hay, _, _ = es_alerta(m.variable, m.valor)
            if hay:
                alertas += 1

        return {
            "total_mediciones": n,
            "estadisticas": {k: asdict(v) for k, v in estadisticas.items()},
            "indice_compuesto": indice_compuesto,
            "indice_zona": indice_zona,
            "alertas_bloque": alertas,
        }

    @staticmethod
    def _suavizar_plano(valores: list[float], intensidad: int) -> list[float]:
        n = len(valores)
        if n == 0:
            return valores
        actual = list(valores)
        for _ in range(intensidad):
            nuevo = [0.0] * n
            for i in range(n):
                izq = actual[i - 1] if i > 0 else actual[i]
                der = actual[i + 1] if i < n - 1 else actual[i]
                nuevo[i] = 0.5 * actual[i] + 0.25 * izq + 0.25 * der
            actual = nuevo
        return actual

    # Fusionar los resultados parciales devueltos por `analizar_bloque`
    @staticmethod
    def combinar_bloques(bloques: list[dict]) -> dict:
        total = 0
        estadisticas: dict[str, dict] = {}
        indice_zona: dict[str, list[float]] = {}
        indice_compuesto_pond = 0.0
        alertas = 0

        for bloque in bloques:
            total += bloque["total_mediciones"]
            alertas += bloque["alertas_bloque"]
            indice_compuesto_pond += bloque["indice_compuesto"] * bloque["total_mediciones"]
            for zona, valor in bloque["indice_zona"].items():
                indice_zona.setdefault(zona, []).append(valor)
            for variable, stats in bloque["estadisticas"].items():
                if variable not in estadisticas:
                    estadisticas[variable] = {
                        "total": 0, "suma_prom": 0.0,
                        "maximo": float("-inf"), "minimo": float("inf"),
                        "suma_var": 0.0,
                    }
                e = estadisticas[variable]
                e["total"] += stats["total_mediciones"]
                e["suma_prom"] += stats["promedio"] * stats["total_mediciones"]
                if stats["maximo"] > e["maximo"]:
                    e["maximo"] = stats["maximo"]
                if stats["minimo"] < e["minimo"]:
                    e["minimo"] = stats["minimo"]
                e["suma_var"] += stats["desviacion"] ** 2 * stats["total_mediciones"]

        estadisticas_final: dict[str, EstadisticasVariable] = {}
        for variable, e in estadisticas.items():
            if e["total"] == 0:
                continue
            estadisticas_final[variable] = EstadisticasVariable(
                variable=variable,
                promedio=e["suma_prom"] / e["total"],
                maximo=e["maximo"],
                minimo=e["minimo"],
                desviacion=(e["suma_var"] / e["total"]) ** 0.5,
                total_mediciones=e["total"],
            )

        indice_zona_final = {
            zona: sum(vals) / len(vals) for zona, vals in indice_zona.items() if vals
        }
        indice_global = indice_compuesto_pond / total if total else 0.0

        return {
            "total_mediciones": total,
            "estadisticas": estadisticas_final,
            "indice_compuesto": indice_global,
            "indice_zona": indice_zona_final,
            "total_alertas": alertas,
        }

    # estadisticas globales agregadas al final de la simulacion
    def resumen(self) -> dict:
        por_variable: dict[str, list[float]] = {}
        for m in self._todas:
            por_variable.setdefault(m.variable, []).append(m.valor)

        estadisticas: dict[str, EstadisticasVariable] = {}
        for variable, valores in por_variable.items():
            estadisticas[variable] = _estadisticas_variable(variable, valores)

        indice_zona: dict[str, float] = {}
        for zona, suma in self._riesgo_acum_zona.items():
            cuenta = self._riesgo_cuenta_zona[zona]
            indice_zona[zona] = suma / cuenta if cuenta else 0.0

        zona_mayor_riesgo: str | None = None
        if indice_zona:
            zona_mayor_riesgo = max(indice_zona, key=indice_zona.get)

        return {
            "total_mediciones": len(self._todas),
            "estadisticas": estadisticas,
            "indice_ambiental": indice_zona,
            "zona_mayor_riesgo": zona_mayor_riesgo,
        }

# Suaviza una lista de filas con el stencil de 3 puntos, `intensidad` pasadas.
# Funcion a nivel de modulo para que sea picklable y la pueda ejecutar un Pool.
def _suavizar_filas(filas: list[list[float]], intensidad: int) -> list[list[float]]:
    resultado: list[list[float]] = []
    for fila in filas:
        longitud = len(fila)
        actual = list(fila)
        for _ in range(intensidad):
            nuevo = [0.0] * longitud
            for j in range(longitud):
                izq = actual[j - 1] if j > 0 else actual[j]
                der = actual[j + 1] if j < longitud - 1 else actual[j]
                nuevo[j] = 0.5 * actual[j] + 0.25 * izq + 0.25 * der
            actual = nuevo
        resultado.append(actual)
    return resultado


# Adaptador para Pool.map: recibe (filas, intensidad) en una sola tupla.
def _suavizar_chunk(args: tuple[list[list[float]], int]) -> list[list[float]]:
    filas, intensidad = args
    return _suavizar_filas(filas, intensidad)


# Divide las filas en a lo sumo n bloques de tamanyo similar conservando el orden.
def _particionar(filas: list[list[float]], n: int) -> list[list[list[float]]]:
    total = len(filas)
    if total == 0:
        return []
    n = max(1, min(n, total))
    tam = (total + n - 1) // n
    return [filas[i:i + tam] for i in range(0, total, tam)]


# promedio, max, min y desviacion con bucles explicitos
def _estadisticas_variable(variable: str, valores: list[float]) -> EstadisticasVariable:
    n = len(valores)
    if n == 0:
        return EstadisticasVariable(variable=variable)
    suma = 0.0
    maximo = valores[0]
    minimo = valores[0]
    for v in valores:
        suma += v
        if v > maximo:
            maximo = v
        if v < minimo:
            minimo = v
    promedio = suma / n
    var_sum = 0.0
    for v in valores:
        d = v - promedio
        var_sum += d * d
    desviacion = (var_sum / n) ** 0.5
    return EstadisticasVariable(
        variable=variable,
        promedio=promedio,
        maximo=maximo,
        minimo=minimo,
        desviacion=desviacion,
        total_mediciones=n,
    )
