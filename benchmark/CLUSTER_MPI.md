# Bitácora de configuración del clúster MPI (Práctica 5)

> Lo que se hizo, lo que falló y cómo se resolvió

## 0. Nodos

| Rol | Equipo | SO | IP |
|-----|--------|----|----|
| head (rank 0, lanza el job) | Felipe | Arch Linux | `192.168.3.72` |
| worker | Sami | Ubuntu | `192.168.3.137` |

Repo clonado en la raíz del home en ambas máquinas (`~/practica-monitoreo-ambiental`), rama `entrega-mpi` (luego mergeada a `main` vía PR #2).

## 1. Red y SSH sin contraseña

- Ambas PCs en la misma red local, `ping` entre ellas sin problema.
- **Primer intento de `ssh-copy-id`** falló por dos motivos, corregidos en
  orden:
  1. `ssh-copy-id samidev@samiDev` — el hostname `samiDev` no resolvía (no había `/etc/hosts` con esos nombres todavía). Solución: usar la IP directamente.
  2. Sin `-i`, `ssh-copy-id` toma las claves de `ssh-add -L` (agente SSH), no necesariamente la clave recién generada. Solución: pasar `-i ~/.ssh/id_ed25519.pub` explícito.
- **`Connection refused` en el puerto 22**: ni la Ubuntu de Sami ni, posteriormente, el propio Arch de Felipe tenían `sshd` corriendo. Se instaló y activó en ambas:
  - Ubuntu: `sudo apt install -y openssh-server && sudo systemctl enable --now ssh`
  - Arch: `sudo pacman -S --needed openssh && sudo systemctl enable --now sshd`
- Importante: `mpiexec` también lanza el proceso **en el propio head** vía SSH (no solo en los workers), así que el head necesitó `ssh-copy-id` y `sshd` **contra sí mismo** también, no solo hacia el worker.
- **Usuarios distintos por máquina** (`felipep` en Arch, `samidev` en Ubuntu): `mpiexec` por defecto intenta conectarse a todos los hosts con el usuario local del head, lo que causaba un cuelgue silencioso (esperando una contraseña sin tener terminal interactiva). Solución: mapear el usuario correcto por IP en `~/.ssh/config` del head:

```
Host 192.168.3.137
    User samidev
```

## 2. Rutas de proyecto distintas por usuario

Como el usuario cambia entre PCs, la ruta absoluta del proyecto también (`/home/felipep/...` vs `/home/samidev/...`), y `mpiexec` envía **una sola línea de comando** a todos los nodos — no puede variar por host. Se resolvió con un symlink idéntico en ambas máquinas:

```bash
sudo ln -s ~/practica-monitoreo-ambiental /opt/practica
```

Así `/opt/practica/.venv/bin/python` es la misma ruta válida en los dos nodos, sin importar el `$HOME` de cada usuario.

## 3. Versión de Open MPI: el problema más largo de resolver

Al hacer la primera prueba cruzada (`mpiexec -n 2 -hostfile hosts.txt uname -n`) apareció:

```
bash: línea 1: prted: orden no encontrada
...
Daemon exit status: 127
```

Causa: **Ubuntu traía Open MPI 4.1.6 de los repos `apt`**, mientras que Arch tenía **5.0.10 de `pacman`**. El daemon de lanzamiento cambió de nombre entre series mayores (`orted` en 4.x → `prted` en 5.x, tras la migración a PRRTE), así que no son binariamente compatibles entre sí.

Solución: compilar Open MPI 5.0.10 **desde el código fuente oficial** en la máquina que se quedó atrás (Ubuntu), en vez de intentar bajar la versión de Arch (no está en AUR de forma simple).

Tras compilarlo en Ubuntu, la prueba cruzada dio un **segundo error**, más sutil:

```
PRTE detected a mismatch in versions between two processes.
Local PRTE version: 3.0.14   (Arch, via pacman)
Peer  PRTE version: 3.0.13   (Ubuntu, compilado desde el tarball oficial)
```

Aunque ambos reportaban "Open MPI 5.0.10", el paquete de `pacman` embebe una versión de PRTE (el runtime de lanzamiento) ligeramente distinta a la del tarball oficial de la web de Open MPI. PRTE exige coincidencia exacta entre todos los nodos de un mismo job. **Lección: "misma versión de Open MPI" no alcanza si una de las dos viene de un paquete de distro y la otra del tarball — hay que compilar ambas desde la misma fuente.**

Solución final: compilar Open MPI 5.0.10 desde el mismo tarball **también en Arch**, quitando antes el paquete de `pacman`:

```bash
sudo pacman -R --noconfirm openmpi
cd /tmp
wget https://download.open-mpi.org/release/open-mpi/v5.0/openmpi-5.0.10.tar.gz
tar xf openmpi-5.0.10.tar.gz
cd openmpi-5.0.10
./configure --prefix=/usr/local --disable-oshmem
CFLAGS="-O1" ...   # ver más abajo, hubo dos bugs de compilación
make -j$(nproc)
sudo make install
sudo ldconfig
```

`--prefix=/usr/local` fue deliberado: en Ubuntu, `/usr/local/bin` está en el `$PATH` por defecto incluso en sesiones SSH no interactivas (a diferencia de rutas en `$HOME`, que dependen de que se cargue el perfil del shell) — evita el problema clásico de `PATH` no cargado que ya se había visto con `uv` en sesiones SSH sin TTY.

## 4. Bugs de compilación en Arch (GCC demasiado nuevo)

Compilar Open MPI 5.0.10 desde fuente en Arch (GCC muy reciente) chocó con dos bugs de compilación distintos, no relacionados con MPI en sí:

1. **`mca/part/persist` — error de inlining agresivo**:
   ```
   error: inlining failed in call to 'always_inline' 'mca_part_persist_start':
   --param max-inline-insns-single limit reached
   ```
   Primer intento: excluir el componente con
   `--enable-mca-no-build=part-persist`. Esto compiló, pero dejó el
   framework `part` **sin ningún componente**, y `part` resultó ser
   obligatorio en `MPI_Init` (mpi4py llama `MPI_Init` al importar el módulo):
   ```
   No components were able to be opened in the part framework.
   ```
   con `EXIT=1` — es decir, MPI no arrancaba en absoluto, no era un simple warning. **Excluir el componente entero fue un error** — la solución correcta era lograr que compilara, no quitarlo.

   Fix real: bajar el nivel de optimización solo para evitar el bug de inlining, dejando el componente activo:
   ```bash
   CFLAGS="-O1" ./configure --prefix=/usr/local --disable-oshmem
   ```

2. **`oshmem/mca/memheap` — error de inicializador con llaves**:
   ```
   error: llaves alrededor del inicializador escalar
   mca_memheap_map_t mca_memheap_base_map = {{{{0}}}};
   ```
   OpenSHMEM (`oshmem`) no se usa en este proyecto (solo se necesita MPI puro). Se resolvió desactivando ese subsistema completo en el configure:
   `--disable-oshmem`.

Comando final de compilación que funcionó en Arch:
```bash
CFLAGS="-O1" ./configure --prefix=/usr/local --disable-oshmem
make -j$(nproc)
sudo make install
sudo ldconfig
```

## 5. `libmpi.so` no encontrado por mpi4py tras compilar

Tras instalar en `/usr/local`, `mpi4py` (que en su versión 4.1.2 no se linkea en build-time sino que hace `dlopen` de `libmpi.so` en tiempo de ejecución) fallaba con:

```
RuntimeError: cannot load MPI library
libmpi.so: cannot open shared object file: No such file or directory
```

Causa: Arch (a diferencia de Ubuntu) no incluye `/usr/local/lib` en la caché de `ldconfig` por defecto. Solución:

```bash
echo "/usr/local/lib" | sudo tee /etc/ld.so.conf.d/openmpi.conf
sudo ldconfig
```

Después de esto, y de recompilar Open MPI con las banderas correctas (`-O1` + `--disable-oshmem`, sin excluir `part`), `mpi4py` cargó correctamente en Arch:

```
Open MPI v5.0.10, package: Open MPI felipep@archlinux Distribution, ...
EXIT=0
```

## 6. Librerías de terceros: sistema vs. interna del tarball (`prrte`, `openpmix`, `hwloc`)

Compilar Open MPI desde el tarball **no basta por sí solo** si la distro ya tiene instaladas, por separado, algunas de las librerías que Open MPI trae empaquetadas internamente (`prrte`, `openpmix`, `hwloc`). El `./configure` las detecta automáticamente vía `pkg-config` y prefiere la del sistema en vez de compilar/instalar su propia copia interna — y si el otro nodo sí usa la interna (o una versión de sistema distinta), aparecen mismatches de versión en cascada, uno detrás de otro, aunque "Open MPI" reporte la misma versión en ambos lados.

Esto se detectó en tres capas sucesivas, cada una con el mismo patrón:

1. **PRTE** (runtime de lanzamiento): tras compilar Open MPI 5.0.10 desde fuente en los dos nodos, seguía apareciendo `PRTE version mismatch (3.0.14 vs 3.0.13)`. Causa: `pacman -Q prrte` mostraba un paquete `prrte 3.0.14-1` instalado aparte de `openmpi` (Arch separa `prrte` como paquete propio). El build usó esa versión externa en vez de la interna del tarball (que es 3.0.13). Solución: `sudo pacman -R --noconfirm prrte` y recompilar.

2. **PMIx**: solucionado el PRTE, apareció un error distinto en el mismo arranque (`PMIX_ERROR` en `plm_base_launch_support.c` / `bfrop_base_unpack.c`, justo al fallar el *handshake* de conexión). Causa: `pacman -Q openpmix` mostraba `openpmix 5.0.11-1` instalado aparte, con `pmix_info` resolviendo a `/usr/bin` en vez de `/usr/local/bin`. Solución: `sudo pacman -R --noconfirm openpmix` y recompilar.

3. **hwloc** (topología de hardware, se intercambia entre nodos al arrancar los daemons): el mismo `PMIX_ERROR` seguía apareciendo, ahora justo después del log `RECEIVED TOPOLOGY SIG ... FROM NODE <worker>` — es decir, fallaba al *desempacar* la firma de topología del nodo remoto. Causa: `pacman -Q hwloc` mostraba `hwloc 2.14.0-1` de sistema, con `lstopo`/ `hwloc-info` resolviendo a `/usr/bin`. A diferencia de `prrte`/`openpmix`, **este paquete sí tenía otro programa dependiendo de él** (`onetbb`), así que no se pudo desinstalar sin más. Solución: en vez de quitar el paquete, forzar a Open MPI a usar su copia interna con un flag de `configure`: ```bash ./configure --prefix=/usr/local --disable-oshmem --with-hwloc=internal ```

**Lección general:** cuando `mpiexec` falle con cualquier mensaje de "version mismatch" o un `PMIX_ERROR` al desempacar datos entre nodos, revisar sistemáticamente qué librerías de terceros embebidas por Open MPI (`prrte`, `openpmix`, `hwloc`, `libevent`, ...) tienen también un paquete de sistema instalado por separado, comparando a qué ruta resuelven sus binarios (`which prted`, `which pmix_info`, `which lstopo` deben apuntar todos a `/usr/local/bin`, no a `/usr/bin`). Si no hay otro paquete que dependa de ellos, se desinstalan; si sí lo hay, se fuerza la copia interna con `--with-<paquete>=internal` en el `configure`.

Además, cada vez que se recompila así, verificar con `hash -r` (o abrir una terminal nueva) que el shell no esté usando una ruta de binario cacheada de antes del cambio — esto generó confusión varias veces durante el proceso.

## 7. `mpiexec` con segmentation fault por parámetros `--mca` mal formados

Al forzar la interfaz de red con nombres de interfaz distintos por nodo (`wlan0` en un nodo, `wlo1` en el otro):

```bash
--mca btl_tcp_if_include wlan0,wlo1 --mca oob_tcp_if_include wlan0,wlo1
```

`mpiexec` truena con `segmentation fault (core dumped)` antes de lanzar nada — incluso con un comando tan simple como `uname -n`. La causa más probable es que la lista se evalúa igual en todos los nodos y, si ninguno de los dos nombres coincide con una interfaz local en algún nodo, el manejo de esa opción no falla con gracia. Como los nombres de interfaz de red **no son estables entre distros/hardware** (`wlan0` vs `wlo1` vs `enp3s0`, etc.), no conviene depender de ellos en un `hostfile`/comando compartido.

Solución: usar notación de subred (CIDR) en vez de nombres de interfaz — es independiente del nombre que tenga la tarjeta de red en cada nodo:

```bash
--mca btl_tcp_if_include 192.168.1.0/24 --mca oob_tcp_if_include 192.168.1.0/24
```

Esto fue necesario porque las máquinas (sobre todo la del head) tenían muchas interfaces de red virtuales (Docker, `br-*`, VPN/libvirt) además de la red real, y Open MPI intentaba usarlas todas para la comunicación de datos (capa BTL, distinta de la capa OOB de lanzamiento), generando warnings como:

```
WARNING: Open MPI accepted a TCP connection from what appears to be a another Open MPI process but cannot find a corresponding process entry for that peer.
```

## 8. Mapeo de procesos: dos hostnames iguales en vez de uno por nodo

Con `hosts.txt` bien configurado (2 IPs, `slots=4` cada una) y todo lo anterior resuelto, `mpiexec -n 2 -hostfile hosts.txt uname -n` igual imprimió el mismo hostname dos veces en vez de uno por nodo. No es un bug: es la política de mapeo por defecto de Open MPI (`--map-by slot`), que llena todos los slots del **primer** nodo del hostfile antes de pasar al siguiente. Como `-n 2` cabe completo dentro de los `slots=4` del primer nodo, nunca toca al segundo.

Solución: pedir reparto explícito por nodo:

```bash
mpiexec -n 2 -hostfile hosts.txt --map-by node ...
```

## 9. Estado actual

- SSH sin contraseña funcionando en ambos sentidos (head→worker y head→sí mismo).
- Open MPI 5.0.10 compilado desde el mismo tarball oficial en las dos máquinas, con `PRTE` coincidente.
- `mpi4py` carga correctamente en ambos nodos (`.venv` reconstruido con `uv sync` después de cada cambio de Open MPI del sistema).
- Symlink `/opt/practica` en ambas PCs apuntando al repo de cada usuario, para tener una única ruta de intérprete válida en el `hostfile`.
- `hosts.txt` en la raíz del repo con las 2 IPs (`192.168.3.72`, `192.168.3.137`), `slots=4` cada una.

**Validado end-to-end** en una prueba de 2 nodos (con los fixes de las secciones 6-8 aplicados): `mpiexec -n 2 -hostfile hosts.txt uname -n` imprime un hostname por nodo, la prueba de mpi4py distribuida funciona (`rank 0`/`rank 1` en hosts distintos), y la corrida real de `mpi_monitoreo.practica_mpi` completa sin errores y agrega el resultado a `resultados/mpi.csv`. Comando final que funcionó (ajustar la subred CIDR a la del clúster real el día de la entrega):

```bash
mpiexec -n <N> -hostfile hosts.txt --map-by node \
  --mca btl_tcp_if_include <SUBRED>/24 --mca oob_tcp_if_include <SUBRED>/24 \
  /opt/practica/.venv/bin/python -m mpi_monitoreo.practica_mpi \
  --estaciones 12 --ciclos 30 --intensidad 4000 --secuencial
```

## 10. Resumen de lecciones para el informe

| Problema | Causa raíz | Solución |
|----------|-----------|----------|
| `ssh-copy-id` no resuelve host | falta `/etc/hosts` | usar IP directamente |
| `ssh-copy-id` no copia la clave correcta | usa `ssh-add -L`, no la clave nueva | pasar `-i` explícito |
| `Connection refused` puerto 22 | `sshd` no instalado/activo | instalar y activar `openssh-server`/`openssh` |
| `mpiexec` se cuelga sin error | usuario local ≠ usuario remoto, sin mapeo SSH | `~/.ssh/config` con `User` por host |
| `mpiexec` se cuelga sin error (variante) | head no puede SSH a sí mismo | `ssh-copy-id` + `sshd` también en el propio head |
| `prted: orden no encontrada` | Open MPI 4.x (Ubuntu/apt) vs 5.x (Arch/pacman) — daemon renombrado | compilar la misma versión desde fuente en el nodo atrasado |
| `PRTE version mismatch` (3.0.14 vs 3.0.13) | incompatibilidad de mismo Open MPI-versión pero distinto build (paquete de distro vs tarball oficial) | compilar **ambos** nodos desde el mismo tarball |
| Error de compilación `part/persist` (inlining) | GCC demasiado agresivo/nuevo en Arch | `CFLAGS=-O1` (no excluir el componente: es obligatorio en `MPI_Init`) |
| Error de compilación `oshmem/memheap` | incompatibilidad de sintaxis C con GCC nuevo | `--disable-oshmem` (no se usa en el proyecto) |
| `libmpi.so: cannot open shared object file` | `/usr/local/lib` no está en la caché de `ldconfig` en Arch | agregar `/etc/ld.so.conf.d/openmpi.conf` + `ldconfig` |
| `PRTE version mismatch` (aun compilando ambos del tarball) | paquete de sistema `prrte` separado, usado como externo por `configure` | `sudo pacman -R --noconfirm prrte` + recompilar |
| `PMIX_ERROR` en el *handshake* de conexión | paquete de sistema `openpmix` separado, usado como externo | `sudo pacman -R --noconfirm openpmix` + recompilar |
| `PMIX_ERROR` justo tras `RECEIVED TOPOLOGY SIG` | `hwloc` de sistema usado como externo (no se pudo quitar: dependencia de `onetbb`) | `--with-hwloc=internal` en el `configure` |
| `mpiexec` con `segmentation fault` al usar `--mca btl_tcp_if_include` | nombres de interfaz de red distintos por nodo (`wlan0` vs `wlo1`) en una lista compartida | usar notación CIDR (`192.168.1.0/24`) en vez de nombres de interfaz |
| `WARNING: ... cannot find a corresponding process entry for that peer` | múltiples interfaces de red virtuales (Docker, VPN, libvirt) confundiendo la capa BTL TCP | restringir con `--mca btl_tcp_if_include <CIDR>` |
| Mismo hostname impreso 2 veces en vez de 1 por nodo | política de mapeo por defecto (`--map-by slot`) llena el primer nodo antes de pasar al siguiente | usar `--map-by node` |
