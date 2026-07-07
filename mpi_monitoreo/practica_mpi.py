"""Entry point SPMD de la version MPI.

Ejecucion local:
    mpiexec -n 4 python -m mpi_monitoreo.practica_mpi --estaciones 8 --ciclos 20

Ejecucion en cluster:
    mpiexec -n 4 -hostfile hosts.txt python -m mpi_monitoreo.practica_mpi ...

Todos los procesos ejecutan el mismo programa. El rank 0 ademas, si se pasa
--secuencial, corre la version secuencial de referencia para calcular el
aceleramiento S = Ts / Tp, imprime el resumen y escribe el CSV.
"""

from __future__ import annotations

import argparse

from mpi4py import MPI

from monitoreo.controlador import ControladorMonitoreo
from monitoreo.eventos import EventoMetricas

from .controlador_mpi import ControladorMPI
from .eventos_json import evento_a_json
from .metricas import eficiencia, escribir_csv, speedup


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Monitoreo ambiental urbano con MPI")
    p.add_argument("--estaciones", type=int, default=8, help="numero de estaciones")
    p.add_argument("--ciclos", type=int, default=20, help="numero de ciclos")
    p.add_argument("--intensidad", type=int, default=2000, help="pasadas de suavizado (carga CPU)")
    p.add_argument("--ventana", type=int, default=10, help="ventana de la media movil")
    p.add_argument("--semilla", type=int, default=1234, help="semilla base de las estaciones")
    p.add_argument("--secuencial", action="store_true", help="correr referencia secuencial (Ts) en rank 0")
    p.add_argument("--salida", default="resultados", help="directorio de los CSV")
    p.add_argument("--no-csv", action="store_true", help="no escribir CSV, solo consola")
    p.add_argument("--emitir", action="store_true", help="emitir eventos JSON a stdout para el feed en vivo de la GUI")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    size = comm.Get_size()

    controlador = ControladorMPI(
        num_estaciones=args.estaciones,
        num_ciclos=args.ciclos,
        intensidad=args.intensidad,
        ventana=args.ventana,
        semilla_base=args.semilla,
        comm=comm,
        emitir=args.emitir,
    )
    resultado = controlador.ejecutar()

    if rank != 0:
        return

    # --- Referencia secuencial (solo rank 0) para el aceleramiento ---
    ts: float | None = None
    if args.secuencial:
        if args.emitir:
            # Linea sin marcador -> la GUI la muestra en el log mientras espera.
            print("Corriendo referencia secuencial (Ts), puede tardar...", flush=True)
        secuencial = ControladorMonitoreo(
            num_estaciones=args.estaciones,
            num_ciclos=args.ciclos,
            intensidad=args.intensidad,
            ventana=args.ventana,
            semilla_base=args.semilla,
        )
        ts = secuencial.ejecutar().tiempo_total

    _reportar(resultado, size, ts)

    if args.emitir:
        _emitir_metricas(resultado, size, ts)

    if not args.no_csv:
        ruta = escribir_csv(resultado, num_procesos=size, ts=ts, salida=args.salida)
        print(f"\nResultado agregado a {ruta}")


# Emite el EventoMetricas final (Tp/Ts/S/E) para la GUI.
def _emitir_metricas(resultado, num_procesos: int, ts: float | None) -> None:
    s = speedup(ts, resultado.tiempo_total)
    print(evento_a_json(EventoMetricas(
        modo=resultado.modo,
        num_procesos=num_procesos,
        num_estaciones=resultado.num_estaciones,
        num_ciclos=resultado.num_ciclos,
        intensidad=resultado.intensidad,
        total_mediciones=resultado.total_mediciones,
        tiempo_paralelo=resultado.tiempo_total,
        tiempo_secuencial=ts,
        speedup=s,
        eficiencia=eficiencia(s, num_procesos),
    )), flush=True)


def _reportar(resultado, num_procesos: int, ts: float | None) -> None:
    s = speedup(ts, resultado.tiempo_total)
    e = eficiencia(s, num_procesos)

    print("=" * 60)
    print(f"  Monitoreo ambiental urbano - MPI ({num_procesos} procesos)")
    print("=" * 60)
    print(f"  Estaciones .............. {resultado.num_estaciones}")
    print(f"  Ciclos .................. {resultado.num_ciclos}")
    print(f"  Intensidad (carga CPU) .. {resultado.intensidad}")
    print(f"  Mediciones procesadas ... {resultado.total_mediciones}")
    print(f"  Alertas generadas ....... {resultado.total_alertas}")
    print(f"  Zona de mayor riesgo .... {resultado.zona_mayor_riesgo}")
    print("-" * 60)
    print(f"  Tiempo paralelo  (Tp) ... {resultado.tiempo_total:.4f} s")
    if ts is not None:
        print(f"  Tiempo secuencial (Ts) .. {ts:.4f} s")
        print(f"  Aceleramiento  S = Ts/Tp  {s:.3f}")
        print(f"  Eficiencia     E = S/N .. {e:.3f}")
    print(f"  Mediciones/segundo ...... {resultado.mediciones_por_segundo:.2f}")
    print("-" * 60)
    print("  Estadisticas por variable:")
    for variable, est in resultado.estadisticas.items():
        print(
            f"    {variable:<12} prom={est.promedio:8.3f}  "
            f"min={est.minimo:8.3f}  max={est.maximo:8.3f}  n={est.total_mediciones}"
        )
    print("=" * 60)


if __name__ == "__main__":
    main()
