"""Smoke test del lado GUI del feed MPI, sin lanzar MPI.

Crea la ventana OCULTA (withdraw), le inyecta en la cola una secuencia de
Eventos que primero se serializan y re-parsean (simulando el viaje por el
stdout del subproceso mpiexec), corre el bucle una vez y verifica que la tabla,
la columna rank, las metricas y el log quedan como se espera.

Ejecutar:  PYTHONPATH=. .venv/bin/python tests/smoke_gui_mpi.py
"""

from __future__ import annotations

import queue
import tkinter as tk

from gui.estilo import aplicar_tema
from gui.ventana_principal import VentanaPrincipal
from monitoreo.eventos import (
    EventoAlerta,
    EventoCicloFin,
    EventoEstadoEstacion,
    EventoFinSimulacion,
    EventoInicio,
    EventoMedicion,
    EventoMetricas,
)
from mpi_monitoreo.eventos_json import evento_a_json, json_a_evento


def _por_el_cable(evento):
    # Simula el viaje real: evento -> linea JSON de stdout -> evento.
    return json_a_evento(evento_a_json(evento))


def main() -> None:
    root = tk.Tk()
    root.withdraw()  # sin ventana visible
    aplicar_tema(root)
    v = VentanaPrincipal(root)

    # Exercita el mostrar/ocultar del subpanel de cluster.
    v.var_modo.set("mpi")
    v._cambio_modo()
    assert v.grupo_mpi.winfo_manager() == "pack", "el subpanel MPI debe mostrarse en modo mpi"

    v.var_ciclos.set(3)
    v._reset_ui()

    estaciones = [("EST-01", "Estacion Centro", "Centro"),
                  ("EST-02", "Estacion Norte", "Norte"),
                  ("EST-03", "Estacion Sur", "Sur"),
                  ("EST-04", "Estacion Centro", "Centro")]
    rank_de = {"EST-01": 0, "EST-02": 1, "EST-03": 0, "EST-04": 1}

    eventos = [EventoInicio("mpi", 4, 3, 50, estaciones)]
    for eid, _n, _z in estaciones:
        eventos.append(EventoEstadoEstacion(eid, "esperando", 0, rank_de[eid]))
    # Dos ranks desincronizados: rank 0 va al ciclo 2, rank 1 al ciclo 1.
    eventos += [
        EventoEstadoEstacion("EST-01", "activa", 2, 0),
        EventoMedicion("EST-01", "Centro", "pm25", 181.3, 2),
        EventoAlerta("EST-01", "Centro", "pm25", 181.3, 150.0, "alto", 0.2, 2),
        EventoCicloFin(2, 0.12, 12, 1, {"Centro": 1.4}),
        EventoEstadoEstacion("EST-02", "activa", 1, 1),
        EventoMedicion("EST-02", "Norte", "co2", 9.1, 1),
        EventoCicloFin(1, 0.15, 12, 0, {"Norte": 0.8}),
        EventoFinSimulacion(3.5, 96, 4, 27.4, "Centro", {"Centro": 1.4, "Norte": 0.8}),
        EventoMetricas("mpi", 2, 4, 3, 50, 96, 3.5, 6.2, 1.77, 0.885),
    ]

    v._cola = queue.Queue()
    v._cola.put(("log", "$ mpiexec -n 2 -hostfile hosts_12.txt ..."))
    for ev in eventos:
        recon = _por_el_cable(ev)
        assert recon is not None, f"no round-trip: {ev}"
        v._cola.put(("evento", recon))
    v._cola.put(("finished", None))

    v._bucle()  # drena la cola una vez
    root.update_idletasks()

    # --- Verificaciones ---
    filas = v.tabla.get_children()
    assert len(filas) == 4, f"esperaba 4 estaciones, hay {len(filas)}"
    assert str(v.tabla.set("EST-01", "rank")) == "0", v.tabla.set("EST-01", "rank")
    assert str(v.tabla.set("EST-02", "rank")) == "1", v.tabla.set("EST-02", "rank")
    assert v.tabla.set("EST-01", "estado") == "activa"
    assert "pm25" in v.tabla.set("EST-01", "ultima")
    # progreso sigue al ciclo mas avanzado (rank 0 -> ciclo 3)
    assert v._ciclo_max == 3, v._ciclo_max
    assert v.lista_alertas.size() == 1, v.lista_alertas.size()
    texto_met = v.lbl_metricas.cget("text")
    assert "Tp" in texto_met and "1.77" in texto_met, texto_met
    assert "6.2" in texto_met, texto_met  # Ts
    log = v.txt_log.get("1.0", tk.END)
    assert "mpiexec" in log, log

    # Ocultar el subpanel al volver a un modo local.
    v.var_modo.set("secuencial")
    v._cambio_modo()
    assert v.grupo_mpi.winfo_manager() == "", "el subpanel MPI debe ocultarse fuera de mpi"

    root.destroy()
    print("OK  smoke_gui_mpi: tabla+rank+alertas+progreso+metricas+log validados end-to-end")


if __name__ == "__main__":
    main()
