# Opción MPI en la GUI

La GUI tkinter (`gui/`) incorpora el modo **`mpi`**: corre la versión distribuida del monitoreo ambiental sobre el clúster y muestra el avance **en vivo**, replicando lo que ya se hacía por consola pero desde la ventana.

---

## Cómo funciona (arquitectura)

La GUI **no puede ser un rank MPI**: un proceso con `mainloop()` de tkinter no
puede a la vez ser uno de los `N` procesos SPMD. Por eso, en modo `mpi`, la GUI
actúa de **lanzador**:

```
[Proceso GUI: python -m gui]  ── subprocess ──▶  [mpiexec -n N -hostfile ... --emitir]
     ventana tkinter                              rank 0 + rank 1..N-1 (las PCs)
          ▲                                                  │
          └────── lee stdout fusionado (pipe) ◀──────────────┘
                  líneas JSON con marcador @EVT@
```

- `gui/worker_mpi.py` (`WorkerMpi`) hace `subprocess.Popen` de `mpiexec ... --emitir` y lee su **stdout fusionado** (todos los ranks) línea a línea.
- Cada rank imprime sus Eventos como una línea JSON precedida de `@EVT@` (`mpi_monitoreo/eventos_json.py`). La GUI las reconstruye y las publica en la **misma `queue.Queue`** que ya consume `VentanaPrincipal._bucle`, así se reutilizan todos los handlers de eventos de los modos secuencial/hilos/procesos.
- Las líneas **sin** marcador (el comando lanzado, warnings de Open MPI, errores de PRTE) se muestran en la pestaña **"Log MPI"**.

**Importante:** el feed es un **canal lateral por stdout**. **No agrega comunicación MPI ni altera la región cronometrada (Tp)** — respeta el diseño "consolidar al final". El truco es que `mpiexec` ya fusiona el stdout de todos los ranks, así que el rank 0 no tiene que recolectar nada de los workers.

**Granularidad: por ciclo.** Cada rank, al cerrar un ciclo, emite el estado y la última medición de sus estaciones, sus alertas y un resumen del ciclo. Como no hay barrera por ciclo, los ranks corren **desincronizados**: en la tabla se ve cada uno avanzar a su ritmo (un nodo con más núcleos va más rápido) — un buen visual de la heterogeneidad del clúster. La barra de progreso sigue al ciclo más avanzado.

---

## Uso

```bash
cd ~/practica-monitoreo-ambiental
python -m gui          # o: uv run python -m gui
```

1. En **Modo** elegí `mpi`. Aparece el subpanel **"Cluster MPI"**.
2. Ajustá los campos:

   | Campo | Qué es |
   |-------|--------|
   | **N procs** | número total de rangos MPI (`mpiexec -n`) |
   | **Hostfile** | uno de `hosts_12/24/36/48.txt` (slots proporcionales a los núcleos) |
   | **Subred** | subred de la red de esa sesión, ej. `192.168.213.0/24` (va en `--mca btl_tcp_if_include`) |
   | **Proyecto** | ruta del proyecto en los nodos, ej. `/opt/practica` (deriva el `python` del venv y el `-wdir`) |
   | **Referencia secuencial (Ts)** | corre además el secuencial para calcular `S = Ts/Tp` y `E = S/N`. Tarda minutos; dejalo apagado si solo querés `Tp` |

   Los spinboxes generales (**Estaciones / Ciclos / Intensidad / Ventana**) también aplican: se pasan como `--estaciones …` al job.
3. **Iniciar**. El comando exacto se imprime en **Log MPI**. La tabla, las alertas y la barra de progreso se llenan en vivo; al terminar, la pestaña **Estadísticas** muestra `Tp` (y `Ts/S/E` si activaste el checkbox) más el resumen consolidado. La corrida agrega su fila a `resultados/mpi.csv` igual que por consola.
4. **Detener** aborta el job (envía `SIGINT` a `mpiexec`, que lo propaga a los ranks).

El comando que arma la GUI equivale a:

```bash
mpiexec -n 12 -hostfile hosts_12.txt --map-by slot --bind-to none \
  -wdir /opt/practica \
  --mca btl_tcp_if_include 192.168.213.0/24 --mca oob_tcp_if_include 192.168.213.0/24 \
  /opt/practica/.venv/bin/python -m mpi_monitoreo.practica_mpi \
  --estaciones 144 --ciclos 100 --intensidad 10000 --emitir
```

---

## El flag `--emitir` (uso por consola)

`practica_mpi.py` acepta `--emitir`: hace que cada rank imprima sus Eventos como líneas `@EVT@{...}` a stdout. Sin el flag, el comportamiento es el de siempre (solo el reporte de texto y el CSV). Prueba rápida de la tubería:

```bash
mpiexec -n 2 .venv/bin/python -m mpi_monitoreo.practica_mpi \
  --estaciones 4 --ciclos 3 --intensidad 50 --emitir --no-csv
```

Debe imprimir líneas `@EVT@{...}` intercaladas con el reporte normal.

---

## Pruebas (sin clúster)

```bash
PYTHONPATH=. .venv/bin/python tests/test_eventos_json.py       # serialización round-trip
PYTHONPATH=. .venv/bin/python tests/test_construir_comando.py  # constructor del comando mpiexec
PYTHONPATH=. .venv/bin/python tests/smoke_gui_mpi.py           # GUI headless con eventos inyectados
```

El smoke test crea la ventana oculta (`withdraw`), le inyecta Eventos serializados+reparseados (simulando el stdout real) y valida tabla, columna rank, alertas, progreso, métricas y log — todo el lado GUI del pipeline sin lanzar MPI.

---

## Problemas comunes en el clúster

Los mismos de las corridas por consola (ver `benchmark/CLUSTER_MPI.md`), que ahora se ven en la pestaña **Log MPI**:

- **`PRTE has lost communication with a remote daemon`**: un nodo perdió el WiFi (frecuente en corridas largas). Reintentar; para el baseline conviene poca carga o correr local.
- **Segfault de `mpiexec` con nombres de interfaz**: usar notación CIDR en el campo **Subred** (`192.168.x.0/24`), no nombres de interfaz.
- **`mpi4py: cannot load MPI library`**: falta registrar `/usr/local/lib` (`ldconfig`) o reconstruir el venv (`uv sync`) tras cambiar el Open MPI del sistema.
- **La subred cambia cada sesión**: actualizar el campo **Subred** al `192.168.x.0/24` de la red del día, o `mpiexec` chocará con interfaces virtuales de Docker/libvirt.
