"""Round-trip de serializacion de Eventos (evento -> JSON -> evento).

Ejecutar:  .venv/bin/python tests/test_eventos_json.py
"""

from __future__ import annotations

from monitoreo.eventos import (
    EventoAlerta,
    EventoCicloFin,
    EventoEstadoEstacion,
    EventoFinSimulacion,
    EventoInicio,
    EventoMedicion,
    EventoMetricas,
)
from mpi_monitoreo.eventos_json import MARCADOR, evento_a_json, json_a_evento

EVENTOS = [
    EventoInicio(
        modo="mpi", num_estaciones=3, num_ciclos=5, intensidad=2000,
        estaciones=[("EST-01", "Estacion Centro", "Centro"),
                    ("EST-02", "Estacion Norte", "Norte")],
    ),
    EventoEstadoEstacion(estacion_id="EST-01", estado="activa", ciclo=2, rank_mpi=1),
    EventoMedicion(estacion_id="EST-02", zona="Norte", variable="pm25", valor=42.5, ciclo=3),
    EventoAlerta(estacion_id="EST-01", zona="Centro", variable="pm25",
                 valor=180.0, umbral=150.0, tipo="alto", severidad=0.2, ciclo=4),
    EventoCicloFin(ciclo=1, tiempo_ciclo=0.123, mediciones_ciclo=18,
                   alertas_ciclo=2, indice_zona={"Centro": 1.5, "Norte": 0.9}),
    EventoFinSimulacion(tiempo_total=12.3, total_mediciones=900, total_alertas=10,
                        mediciones_por_segundo=73.1, zona_mayor_riesgo="Centro",
                        indice_ambiental={"Centro": 1.5}),
    EventoMetricas(modo="mpi", num_procesos=12, num_estaciones=144, num_ciclos=100,
                   intensidad=10000, total_mediciones=86400, tiempo_paralelo=145.9,
                   tiempo_secuencial=1088.9, speedup=7.46, eficiencia=0.62),
    # EventoMetricas sin referencia secuencial (Ts/S/E en None).
    EventoMetricas(modo="mpi", num_procesos=12, num_estaciones=144, num_ciclos=100,
                   intensidad=10000, total_mediciones=86400, tiempo_paralelo=145.9),
]


def test_roundtrip():
    for ev in EVENTOS:
        linea = evento_a_json(ev)
        assert linea.startswith(MARCADOR), linea
        assert "\n" not in linea, "el evento debe caber en una sola linea"
        recon = json_a_evento(linea)
        assert recon == ev, f"\n esperado: {ev}\n obtenido: {recon}"


def test_marcador_en_medio():
    # Simula el prefijo [host:rank] de --tag-output y ruido antes del marcador.
    ev = EventoEstadoEstacion(estacion_id="EST-09", estado="activa", ciclo=7, rank_mpi=3)
    linea = "[archlinux:00003] " + evento_a_json(ev)
    assert json_a_evento(linea) == ev


def test_lineas_no_evento():
    for basura in [
        "",
        "--------------------------------------------------------------",
        "  Monitoreo ambiental urbano - MPI (12 procesos)",
        "prterun: PRTE has lost communication with a remote daemon.",
        "@EVT@{roto sin cerrar",           # marcador pero JSON invalido
        '@EVT@{"_tipo": "NoExiste"}',       # tipo desconocido
        '@EVT@{"_tipo": "EventoMedicion"}',  # faltan campos obligatorios
    ]:
        assert json_a_evento(basura) is None, f"deberia ser None: {basura!r}"


if __name__ == "__main__":
    test_roundtrip()
    test_marcador_en_medio()
    test_lineas_no_evento()
    print("OK  eventos_json:", len(EVENTOS), "eventos round-trip + tolerancia a ruido")
