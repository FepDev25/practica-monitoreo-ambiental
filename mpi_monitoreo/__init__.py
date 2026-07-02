"""Version MPI (mpi4py) del sistema de monitoreo ambiental.

Reutiliza el dominio del paquete `monitoreo` (estaciones, mediciones,
analizador, alertas) y le agrega un controlador SPMD que distribuye las
estaciones entre procesos MPI y consolida los resultados en el rank 0.
"""
