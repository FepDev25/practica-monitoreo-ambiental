# Resultados de las pruebas — Versión MPI (Práctica 5)

Registro de las corridas de rendimiento del sistema de monitoreo ambiental distribuido con MPI. Bitácora de armado del clúster (SSH, compilación de Open MPI, problemas resueltos) en `CLUSTER_MPI.md`. Datos crudos en `../resultados/mpi.csv`.

## 1. Entorno

- Python 3.14t (free-threading) + mpi4py 4.1.2 + numpy 2.5.0.
- **Open MPI 5.0.10** compilado desde el mismo tarball en los 3 nodos (mismo `prted`/`pmix`/`hwloc`, sin mismatches).
- Descomposición **por estaciones** (round-robin): cada rango simula su lote de estaciones y corre el análisis pesado (`_suavizar_filas`) sobre ellas; el rank 0 consolida al final. Comms: `bcast`, `scatter`, `isend/recv`, `gather`, `Reduce`, `Barrier`.

## 2. Clúster (3 nodos físicos — universidad, red `192.168.213.0/24`)

| Nodo | Hostname | IP | Usuario | Núcleos | Slots | Red |
|------|----------|-----|---------|---------|-------|-----|
| Head (rank 0) | `archlinux` | 192.168.213.207 | felipep | 20 (i9-13900H) | 18 | Wifi |
| Worker | `samiDev` | 192.168.213.137 | samidev | 24 | 18 | Wifi |
| Worker | `JosePC` | 192.168.213.9 | josea | 12 | 12 | Wifi |

Total: **48 slots**. Symlink idéntico `/opt/practica` en los 3; se usa siempre `/opt/practica/.venv/bin/python`.

### Comando base

```bash
mpiexec -n <N> -hostfile hosts.txt --map-by slot --bind-to none --wdir /opt/practica \
  --mca btl_tcp_if_include 192.168.213.0/24 \
  --mca oob_tcp_if_include 192.168.213.0/24 \
  /opt/practica/.venv/bin/python -m mpi_monitoreo.practica_mpi \
  --estaciones <E> --ciclos <C> --intensidad <I> [--secuencial]
```

- `--secuencial`: rank 0 corre además la referencia de 1 núcleo (`Ts`). Solo para medir el baseline; en el sweep se omite (mide solo `Tp`, mucho más rápido).
- `--map-by slot` (empaca) para **llenar núcleos**; `--map-by node` (reparte 1/nodo) solo para ver hostnames o repartir parejo entre las 3 máquinas.
- `--bind-to none` evita el error `Out of resource` / `Binding policy: NUMA`.

## 3. Pruebas realizadas

### 3.1 Validación local (una sola máquina, Arch 20 núcleos)

Equivalencia MPI ≡ secuencial y escalado intra-nodo. Carga: 12 est / 30 ciclos
/ intensidad 4000.

| N | Ts (s) | Tp (s) | S = Ts/Tp | E = S/N |
|---|--------|--------|-----------|---------|
| 1 | 16.162 | 16.158 | 1.000 | 1.000 |
| 2 | 16.350 | 9.440 | 1.732 | 0.866 |
| 4 | 16.761 | 5.225 | 3.208 | 0.802 |

Escalado limpio dentro de un nodo; E baja suave con N (contención de memoria/caché).

### 3.2 Clúster 2 nodos (Felipe + Sami, WiFi)

| N | Estaciones | Ciclos | Int. | Ts (s) | Tp (s) | S | E | Nota |
|---|-----------|--------|------|--------|--------|---|---|------|
| 2 | 12 | 30 | 4000 | 6.587 | 3.333 | 1.976 | 0.988 | Primera corrida cruzada real |
| 2 | 24 | 100 | 10000 | 129.615 | 60.485 | 2.143 | **1.071** | Superlineal (ver §4) |
| 36 | 72 | 100 | 10000 | — | 72.578 | *pend.* | *pend.* | Llenando núcleos (18+18) |

### 3.3 Clúster 3 nodos (Felipe + Sami + Jose/WiFi) — HITO

| N | Estaciones | Ciclos | Int. | Ts (s) | Tp (s) | S | E | Nodos usados |
|---|-----------|--------|------|--------|--------|---|---|--------------|
| 3 | 24 | 60 | 8000 | 63.038 | 25.754 | 2.448 | 0.816 | 3 (1 proc/nodo) |
| 12 | 144 | 100 | 10000 | *pend.* | 274.272 | *pend.* | *pend.* | **Solo Felipe** (map-by slot empaca) |
| 48 | 144 | 100 | 10000 | *pend.* | 84.691 | *pend.* | *pend.* | 3 (18+18+12) |

> `Ts` para la carga 144/100/10000 en medición (~10-12 min en 1 núcleo);
> al tenerlo se completan las columnas S/E de estas filas.

## 4. Observaciones clave (para el análisis del informe)

1. **Speedup superlineal (E>1) con 2 nodos.** Con 24 est / int 10000, E=1.071. Causas: (a) *working set* más chico por nodo → mejor caché; (b) baseline `Ts` medido en una sola máquina vs cómputo repartido en hardware heterogéneo. Es una limitación metodológica esperable, no un error.

2. **La eficiencia cae al cruzar el clúster.** N=3 en 3 nodos da E=0.816 (vs ~0.99 en 2 nodos balanceados). Los **3 nodos están por WiFi** (latencia ~9-20 ms, contra <1 ms de memoria local). El `Barrier` hace que el **nodo más lento marque `Tp`**; con nodos desiguales (20/24/12 núcleos), el más chico (Jose, 12 núcleos) arrastra el tiempo, sumado al overhead de red WiFi compartido entre las 3 máquinas.

   > **Toda la red es WiFi** — nunca se usó cable. Es una fuente importante de overhead y de variabilidad (ver obs. 7).

3. **Dónde caen los rangos importa** (`--map-by slot` empaca): N≤18 corre solo en Felipe; N=19–36 añade a Sami; N=37–48 entra Jose/WiFi. Por eso N=12 (274 s) corrió **entero en Felipe** sin tocar el clúster. Hay que anotar la ubicación junto a cada `Tp` porque explica la forma de la curva.

4. **El `Ts` (baseline) es 1 núcleo en rank 0** y domina el tiempo de reloj de una corrida con `--secuencial` (p.ej. ~130 s para 24 est, ~10 min para 144). Se mide UNA vez por carga; el sweep de N va sin `--secuencial`.

5. **Coste del análisis ∝ estaciones_locales × ventana × intensidad** por ciclo (`_suavizar_filas`, `monitoreo/analizador.py`). Grano fino (pocas estaciones por rango) → domina el overhead (arranque de intérpretes, `recv`, `Barrier`) y la curva de speedup se aplana.

6. **Laptops a batería throttlean** (visto 1.9 GHz en el i9-13900H, debería ~5 GHz) → tiempos no reproducibles. Correr **enchufados** para la batería oficial.

7. **El WiFi puede tirar la corrida.** En corridas largas (~13 min) el daemon ocioso de un nodo perdió el WiFi y PRTE abortó todo el job (`PRTE has lost communication with a remote daemon`). Mitigaciones: (a) medir el `Ts` y las corridas de N≤18 **localmente en un nodo** (sin `hostfile`, no dependen de la red); (b) mantener las corridas distribuidas cortas; (c) reintentar si cae.

## 5. Batería oficial del informe

> **NORMA DEL PROYECTO: todas las pruebas usan las 3 máquinas.** No se reportan corridas de 1 o 2 nodos (las de §3.1 y §3.2 quedan solo como historial del armado). Cada corriente reparte rangos en Felipe + Sami + Jose.

**Estrategia:** slots **proporcionales a los núcleos** (ratio 4:5:3 ≈ 20:24:12) para que las 3 máquinas trabajen balanceadas y terminen juntas (Tp limpio, no arrastrado por un split desigual). Un hostfile por N: `hosts_12/24/36/48.txt`. Carga fija: **144 est / 100 ciclos / intensidad 10000**, `--map-by slot --bind-to none`, sin `--secuencial`.

| N | Hostfile | Felipe | Sami | Jose | Est./rango | Tp (s) | S=Ts/Tp | E=S/N |
|---|----------|--------|------|------|-----------|--------|---------|-------|
| 12 | `hosts_12.txt` | 4 | 5 | 3 | 12 | 145.961 | **7.46** | **0.622** |
| 24 | `hosts_24.txt` | 8 | 10 | 6 | 6 | 128.728 | **8.46** | **0.352** |
| 36 | `hosts_36.txt` | 12 | 15 | 9 | 4 | 97.740 | **11.14** | **0.309** |
| 48 | `hosts_48.txt` | 16 | 20 | 12 | 3 | 99.009 | **11.00** | **0.229** |

Con `Ts = 1088.960 s` (baseline secuencial de 1 núcleo). `S = Ts/Tp`, `E = S/N`.
**Máximo aceleramiento en N=36 (S=11.14×)**; en N=48 baja (S=11.00×) por la
saturación descrita abajo. La eficiencia cae de 0.62 (N=12) a 0.23 (N=48).

Datos crudos en `../resultados/mpi.csv` (filas 144/100/10000).
- N=36 se corrió dos veces (97.74 s y 100.62 s) → variabilidad ~3% entre corridas, típica de red WiFi compartida.
- Existe además un N=48 con reparto **18/18/12** (84.69 s), distinto del proporcional 16/20/12 (99.01 s): **la distribución de slots cambia el Tp** hasta ~15% aun con el mismo total de procesos → el balance de carga importa.

**Escalado (Tp, misma carga):** 145.96 → 128.73 → 97.74 → 99.01 s de N=12 a 48. La curva **mejora hasta N=36 y luego se satura** (N=48 ≈ N=36, incluso peor). Al subir procesos: (a) el grano se hace fino (12→3 est/rango), (b) crece el overhead de comunicación/`Barrier` sobre WiFi compartido, y (c) a N=48 Jose queda **saturado (12 rangos / 12 núcleos, sin holgura)** y arrastra el `Tp`. Es el punto de rendimientos decrecientes clásico del *strong scaling* en un clúster WiFi heterogéneo: hay speedup absoluto pero la eficiencia por proceso se desploma.

### Baseline (medido en 1 núcleo local, máquina en reposo)

Una sola corrida `-n 1 --secuencial` produce **dos** números útiles:

| Métrica | Tiempo (s) | Qué es |
|---------|-----------|--------|
| `Ts` (secuencial puro) | **1088.960** | `ControladorMonitoreo`, sin MPI |
| `Tp(N=1)` (MPI, 1 proc) | **809.720** | `ControladorMPI` con `size=1` |

> ⚠️ **Ojo metodológico:** el código MPI en 1 núcleo (809.72 s) es **~26% más
> rápido** que el secuencial puro (1088.96 s) — misma cuenta, distinto camino de
> código (el MPI es más liviano). Por eso parte del "speedup" viene de una
> implementación mejor, no solo del paralelismo. Dos lecturas legítimas:
> - **vs secuencial** (`Ts=1088.96`) — la de la tabla; mide el beneficio total.
> - **vs MPI-1-proceso** (`Tp(1)=809.72`) — mide el *escalado puro* del código
>   paralelo (S: 5.55→6.29→8.28→8.18 para N=12/24/36/48). El informe puede
>   reportar ambas y explicar la diferencia.

Comando (contaminación cero: máquina sola, un único proceso, enchufada):
```bash
cd ~/practica-monitoreo-ambiental
/opt/practica/.venv/bin/python -m mpi_monitoreo.practica_mpi \
  --estaciones 144 --ciclos 100 --intensidad 10000 --secuencial
```

> **Anécdota para el informe:** las 4 corridas paralelas (incluso N=12) terminaron **antes** que el `Ts` de 1 núcleo — la mejor evidencia visual del paralelismo: 48 procesos en 3 PCs acaban mientras 1 solo núcleo sigue crunchendo las 144 estaciones.

**Extras (todos con las 3 máquinas):**
- [ ] Barrido de `intensidad` (2000/5000/10000/20000) con N=48 fijo → relación cómputo/overhead (a más cómputo, mejor E — dilución del overhead WiFi).
- [ ] Capturas de `bpytop` de los 3 nodos con los núcleos activos (evidencia visual del paralelismo real y del balance de carga proporcional).
