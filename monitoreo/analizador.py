from __future__ import annotations

from collections import deque
from dataclasses import asdict

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
        tensor = [0.0] * (num_series * longitud)

        for i, (clave, serie) in enumerate(series):
            estacion_id, variable = clave
            cfg = VARIABLES[variable]
            base = i * longitud
            valores = list(serie)
            for j in range(longitud):
                if j < len(valores):
                    tensor[base + j] = cfg.riesgo(valores[j])
                elif j > 0:
                    tensor[base + j] = tensor[base + j - 1]
                else:
                    tensor[base + j] = 0.0

        tensor = self._suavizar_tensor(tensor, num_series, longitud, self.intensidad)

        riesgo_por_estacion: dict[str, float] = {}
        cuenta_por_estacion: dict[str, int] = {}
        for i, (clave, _) in enumerate(series):
            estacion_id = clave[0]
            actual = tensor[i * longitud + longitud - 1]
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

    # pasadas de suavizado 3 puntos sobre el tensor para carga CPU
    @staticmethod
    def _suavizar_tensor(tensor: list[float], num_series: int, longitud: int, intensidad: int,) -> list[float]:
        if num_series == 0 or longitud == 0:
            return tensor
        actual = tensor
        for _ in range(intensidad):
            nuevo = [0.0] * (num_series * longitud)
            for i in range(num_series):
                base = i * longitud
                for j in range(longitud):
                    izq = actual[base + j - 1] if j > 0 else actual[base + j]
                    der = actual[base + j + 1] if j < longitud - 1 else actual[base + j]
                    nuevo[base + j] = 0.5 * actual[base + j] + 0.25 * izq + 0.25 * der
            actual = nuevo
        return actual

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
