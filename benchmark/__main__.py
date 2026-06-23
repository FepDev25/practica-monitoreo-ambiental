"""Punto de entrada del benchmark: `python -m benchmark [opciones]`."""

from __future__ import annotations

import argparse

from monitoreo.entorno import resumen_entorno
from benchmark.runner import (
    CONFIGURACIONES_POR_DEFECTO,
    correr_benchmark,
    guardar_csv,
    tabla_resumen,
)


def _parsear_configuraciones(texto: str) -> tuple[tuple[int, int], ...]:
    """Parsea '4x10,8x20,12x30' -> ((4,10),(8,20),(12,30))."""
    configs = []
    for parte in texto.split(","):
        parte = parte.strip()
        if not parte:
            continue
        if "x" not in parte:
            raise argparse.ArgumentTypeError(
                f"Configuracion invalida: {parte!r}. Use formato NxM."
            )
        est, cic = parte.split("x", 1)
        configs.append((int(est), int(cic)))
    if not configs:
        raise argparse.ArgumentTypeError("Debe indicar al menos una configuracion.")
    return tuple(configs)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark del sistema de monitoreo ambiental "
        "(secuencial / hilos / procesos)."
    )
    parser.add_argument(
        "--configuraciones",
        type=_parsear_configuraciones,
        default=",".join(f"{e}x{c}" for e, c in CONFIGURACIONES_POR_DEFECTO),
        help="Tamanyos a probar, formato NxM. Por defecto 4x10,8x20,12x30.",
    )
    parser.add_argument(
        "--repeticiones", type=int, default=3,
        help="Veces que se ejecuta cada version por configuracion (default 3).",
    )
    parser.add_argument(
        "--intensidad", type=int, default=2000,
        help="Pasadas de suavizado (carga de CPU) del analizador (default 2000).",
    )
    parser.add_argument(
        "--ventana", type=int, default=10,
        help="Ventana de la media movil en ciclos (default 10).",
    )
    parser.add_argument(
        "--modo", choices=["secuencial", "hilos", "procesos"], default=None,
        help="Ejecutar solo un modo (para pruebas rapidas). Por defecto todos.",
    )
    parser.add_argument(
        "--salida", default="resultados",
        help="Directorio donde se guardan los CSV (default resultados).",
    )
    parser.add_argument(
        "--no-csv", action="store_true",
        help="No guardar resultados en CSV (solo mostrar en consola).",
    )
    args = parser.parse_args()

    print("Entorno:", resumen_entorno())
    modos = [args.modo] if args.modo else None

    ejecuciones, resumenes, entorno = correr_benchmark(
        configuraciones=args.configuraciones,
        repeticiones=args.repeticiones,
        intensidad=args.intensidad,
        ventana=args.ventana,
        modos_permitidos=modos,
        progreso=lambda m: print(m),
    )

    print("\n=== Resumen comparativo ===")
    print(tabla_resumen(resumenes))

    if not args.no_csv:
        paths = guardar_csv(ejecuciones, resumenes, entorno, args.salida)
        print(f"\nCSV guardados en {args.salida}/:")
        print(f"  {paths[0]}  (ejecuciones)")
        print(f"  {paths[1]}  (resumen)")
        print(f"  {paths[2]}  (entorno)")


if __name__ == "__main__":
    main()
