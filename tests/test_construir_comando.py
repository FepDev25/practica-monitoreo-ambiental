"""Constructor del comando mpiexec de la GUI (funcion pura).

Ejecutar:  .venv/bin/python tests/test_construir_comando.py
"""

from __future__ import annotations

from gui.worker_mpi import construir_comando

BASE = dict(estaciones=12, ciclos=30, intensidad=2000, ventana=10, semilla=1234,
            secuencial=False)


def test_local_sin_hostfile():
    cmd = construir_comando(n=4, hostfile="", **BASE)
    assert cmd[:3] == ["mpiexec", "-n", "4"]
    # Sin hostfile no van los flags de cluster.
    for flag in ("-hostfile", "--map-by", "--bind-to", "-wdir", "btl_tcp_if_include"):
        assert flag not in cmd, flag
    assert "-m" in cmd and "mpi_monitoreo.practica_mpi" in cmd
    assert "--emitir" in cmd
    assert "--secuencial" not in cmd


def test_cluster_con_hostfile_y_subred():
    cmd = construir_comando(
        n=12, hostfile="hosts_12.txt", subred="192.168.213.0/24",
        proyecto="/opt/practica", **BASE,
    )
    s = " ".join(cmd)
    assert "-hostfile hosts_12.txt" in s
    assert "--map-by slot" in s
    assert "--bind-to none" in s
    assert "-wdir /opt/practica" in s
    assert "--mca btl_tcp_if_include 192.168.213.0/24" in s
    assert "--mca oob_tcp_if_include 192.168.213.0/24" in s
    # Python del venv derivado del proyecto.
    assert "/opt/practica/.venv/bin/python" in cmd


def test_python_bin_explicito_gana():
    cmd = construir_comando(n=2, hostfile="", python_bin="/usr/bin/python3", **BASE)
    assert "/usr/bin/python3" in cmd
    assert "/.venv/bin/python" not in " ".join(cmd)


def test_secuencial_agrega_flag():
    args = {**BASE, "secuencial": True}
    cmd = construir_comando(n=3, hostfile="hosts_12.txt", **args)
    assert "--secuencial" in cmd


def test_parametros_de_simulacion():
    cmd = construir_comando(n=1, hostfile="", estaciones=8, ciclos=20,
                            intensidad=4000, ventana=7, semilla=99, secuencial=False)
    s = " ".join(cmd)
    assert "--estaciones 8" in s
    assert "--ciclos 20" in s
    assert "--intensidad 4000" in s
    assert "--ventana 7" in s
    assert "--semilla 99" in s


if __name__ == "__main__":
    test_local_sin_hostfile()
    test_cluster_con_hostfile_y_subred()
    test_python_bin_explicito_gana()
    test_secuencial_agrega_flag()
    test_parametros_de_simulacion()
    print("OK  construir_comando: 5 casos (local, cluster, venv, secuencial, params)")
