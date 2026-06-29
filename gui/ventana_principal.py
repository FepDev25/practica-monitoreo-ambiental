# Ventana principal de la GUI del sistema de monitoreo ambiental (tkinter)

from __future__ import annotations

import queue
import time
import tkinter as tk
from collections import deque
from tkinter import ttk

from benchmark.runner import descubrir_controladores
from gui.estilo import COLORS, ESTADO_BG, ESTADO_FG
from gui.worker_simulacion import WorkerSimulacion
from monitoreo.config import VARIABLES
from monitoreo.entorno import info_entorno
from monitoreo.eventos import (
    EventoAlerta,
    EventoCicloFin,
    EventoEstadoEstacion,
    EventoFinSimulacion,
    EventoInicio,
    EventoMedicion,
)

COLUMNAS = ("id", "zona", "estado", "ultima", "ciclo")
ENCABEZADOS = {
    "id": "ID",
    "zona": "Zona",
    "estado": "Estado",
    "ultima": "Ultima medicion",
    "ciclo": "Ciclo",
}
CLAVES_ENTORNO = (
    "python", "implementacion", "sistema", "release",
    "maquina", "cpu_count", "gil_habilitado", "build_free_threading",
)


class VentanaPrincipal:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Monitoreo Ambiental Urbano - Cuenca")
        self.root.geometry("1200x760")
        self.root.minsize(960, 600)

        self._worker: WorkerSimulacion | None = None
        self._cola: queue.Queue = queue.Queue()
        self._controladores = descubrir_controladores()
        self._t_inicio: float = 0.0
        self._cron_activo = False
        self._ultimas_alertas: deque[str] = deque(maxlen=200)

        self._construir_ui()
        self._poblar_entorno()

        self.root.protocol("WM_DELETE_WINDOW", self._al_cerrar)
        # Bucle unico: drena la cola de eventos y refresca el cronometro
        self.root.after(50, self._bucle)

    # ------------------------------------------------------------------ UI
    def _construir_ui(self) -> None:
        cont = ttk.Frame(self.root, padding=10)
        cont.pack(fill="both", expand=True)

        # Cabecera
        ttk.Label(
            cont, text="Sistema de Monitoreo Ambiental Urbano - Cuenca",
            style="Titulo.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            cont,
            text="Simulacion de estaciones con paralelismo: secuencial / hilos / procesos",
            style="Subtitulo.TLabel",
        ).pack(anchor="w", pady=(0, 8))

        self._panel_controles(cont)

        principal = ttk.Frame(cont)
        principal.pack(fill="both", expand=True, pady=(8, 0))
        self._panel_estaciones(principal)
        self._panel_resultados(principal)

        # Barra de estado
        self.status = ttk.Label(cont, text="Listo.", style="Estado.TLabel", anchor="w")
        self.status.pack(fill="x", pady=(8, 0), ipady=4)

    def _panel_controles(self, padre) -> None:
        grupo = ttk.LabelFrame(padre, text="Configuracion de la simulacion", padding=8)
        grupo.pack(fill="x")

        fila = ttk.Frame(grupo)
        fila.pack(fill="x")

        modos = [m for m in ("secuencial", "hilos", "procesos") if m in self._controladores]
        self.var_modo = tk.StringVar(value="secuencial")
        ttk.Label(fila, text="Modo:").pack(side="left")
        self.cb_modo = ttk.Combobox(
            fila, textvariable=self.var_modo, values=modos,
            state="readonly", width=12,
        )
        self.cb_modo.pack(side="left", padx=(4, 12))
        self.cb_modo.bind("<<ComboboxSelected>>", self._cambio_modo)

        self.var_estaciones = tk.IntVar(value=4)
        self.var_ciclos = tk.IntVar(value=10)
        self.var_intensidad = tk.IntVar(value=2000)
        self.var_ventana = tk.IntVar(value=10)

        self._spin(fila, "Estaciones:", self.var_estaciones, 1, 24, 1)
        self._spin(fila, "Ciclos:", self.var_ciclos, 1, 200, 1)
        self._spin(fila, "Intensidad CPU:", self.var_intensidad, 1, 20000, 100)
        self._spin(fila, "Ventana MM:", self.var_ventana, 1, 100, 1)

        self.lbl_cron = ttk.Label(fila, text="0.000 s", style="Cron.TLabel")
        self.lbl_cron.pack(side="left", padx=(12, 6))

        self.btn_detener = ttk.Button(
            fila, text="Detener", style="Detener.TButton",
            command=self._detener, state="disabled",
        )
        self.btn_detener.pack(side="right")
        self.btn_iniciar = ttk.Button(
            fila, text="Iniciar", style="Iniciar.TButton", command=self._iniciar,
        )
        self.btn_iniciar.pack(side="right", padx=(0, 6))
        self.lbl_modo_actual = ttk.Label(fila, text="modo: secuencial", style="Modo.TLabel")
        self.lbl_modo_actual.pack(side="right", padx=(0, 12))

    def _spin(self, padre, etiqueta, var, desde, hasta, paso) -> None:
        ttk.Label(padre, text=etiqueta).pack(side="left")
        ttk.Spinbox(
            padre, from_=desde, to=hasta, increment=paso,
            textvariable=var, width=7,
        ).pack(side="left", padx=(4, 12))

    def _panel_estaciones(self, padre) -> None:
        grupo = ttk.LabelFrame(padre, text="Estaciones ambientales", padding=6)
        grupo.pack(side="left", fill="both", expand=True, padx=(0, 5))

        tabla = ttk.Frame(grupo)
        tabla.pack(fill="both", expand=True)
        self.tabla = ttk.Treeview(
            tabla, columns=COLUMNAS, show="headings", selectmode="browse",
        )
        for col in COLUMNAS:
            self.tabla.heading(col, text=ENCABEZADOS[col])
            ancho = 220 if col == "ultima" else 90
            self.tabla.column(col, width=ancho, anchor="w", stretch=(col == "ultima"))
        scroll = ttk.Scrollbar(tabla, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        # Tags de color por estado de estacion
        for estado, bg in ESTADO_BG.items():
            self.tabla.tag_configure(
                f"estado_{estado}", background=bg,
                foreground=ESTADO_FG.get(estado, COLORS["texto"]),
            )

        prog = ttk.Frame(grupo)
        prog.pack(fill="x", pady=(6, 0))
        self.progreso = ttk.Progressbar(prog, maximum=10, value=0)
        self.progreso.pack(side="left", fill="x", expand=True)
        self.lbl_progreso = ttk.Label(prog, text="Ciclo 0 / 0")
        self.lbl_progreso.pack(side="left", padx=(8, 0))

    def _panel_resultados(self, padre) -> None:
        grupo = ttk.LabelFrame(padre, text="Resultados en vivo", padding=6)
        grupo.pack(side="right", fill="both", expand=True, padx=(5, 0))

        tabs = ttk.Notebook(grupo)
        tabs.pack(fill="both", expand=True)

        # Pestaña Alertas
        tab_alertas = ttk.Frame(tabs, padding=4)
        cont_lista = ttk.Frame(tab_alertas)
        cont_lista.pack(fill="both", expand=True)
        self.lista_alertas = tk.Listbox(
            cont_lista, bg="#FFFDE7", fg=COLORS["texto"],
            highlightthickness=1, highlightbackground="#FFE082",
            borderwidth=0, activestyle="none", font=("DejaVu Sans", 9),
        )
        scr_al = ttk.Scrollbar(cont_lista, orient="vertical", command=self.lista_alertas.yview)
        self.lista_alertas.configure(yscrollcommand=scr_al.set)
        self.lista_alertas.pack(side="left", fill="both", expand=True)
        scr_al.pack(side="right", fill="y")
        self.lbl_contador_alertas = ttk.Label(tab_alertas, text="Alertas activas: 0")
        self.lbl_contador_alertas.pack(anchor="w", pady=(4, 0))
        tabs.add(tab_alertas, text="Alertas")

        # Pestaña Estadisticas
        tab_stats = ttk.Frame(tabs, padding=8)
        self.lbl_stats = ttk.Label(
            tab_stats, text="Sin datos aun. Ejecute una simulacion.",
            anchor="nw", justify="left", wraplength=420,
            background=COLORS["papel"],
        )
        self.lbl_stats.pack(fill="both", expand=True)
        tabs.add(tab_stats, text="Estadisticas")

        # Pestaña Entorno
        tab_entorno = ttk.Frame(tabs, padding=8)
        self.lbls_entorno: dict[str, ttk.Label] = {}
        for i, clave in enumerate(CLAVES_ENTORNO):
            ttk.Label(
                tab_entorno, text=clave.replace("_", " ").capitalize() + ":",
                anchor="e", font=("DejaVu Sans", 10, "bold"),
                background=COLORS["papel"],
            ).grid(row=i, column=0, sticky="e", padx=(0, 10), pady=3)
            val = ttk.Label(tab_entorno, text="-", anchor="w", background=COLORS["papel"])
            val.grid(row=i, column=1, sticky="w", pady=3)
            self.lbls_entorno[clave] = val
        tabs.add(tab_entorno, text="Entorno")

    # -------------------------------------------------------------- Entorno
    def _poblar_entorno(self) -> None:
        e = info_entorno()
        gil = e["gil_habilitado"]
        gil_txt = (
            "Si (GIL activo)" if gil is True
            else "No (free-threading)" if gil is False
            else "no determinable"
        )
        textos = {
            "python": e["python"],
            "implementacion": e["implementacion"],
            "sistema": e["sistema"],
            "release": e["release"],
            "maquina": e["maquina"],
            "cpu_count": str(e["cpu_count"]),
            "gil_habilitado": gil_txt,
            "build_free_threading": "Si" if e["build_free_threading"] else "No",
        }
        for clave, lbl in self.lbls_entorno.items():
            lbl.config(text=textos.get(clave, "-"))

    # ------------------------------------------------------------- Controles
    def _cambio_modo(self, _evt=None) -> None:
        self.lbl_modo_actual.config(text=f"modo: {self.var_modo.get()}")

    def _iniciar(self) -> None:
        modo = self.var_modo.get()
        clase = self._controladores.get(modo)
        if clase is None:
            self.status.config(text=f"Modo {modo!r} no disponible.")
            return
        self._reset_ui()
        self.btn_iniciar.config(state="disabled")
        self.btn_detener.config(state="normal")
        self._t_inicio = time.perf_counter()
        self._cron_activo = True

        self._cola = queue.Queue()
        self._worker = WorkerSimulacion(
            clase_controlador=clase,
            num_estaciones=self.var_estaciones.get(),
            num_ciclos=self.var_ciclos.get(),
            intensidad=self.var_intensidad.get(),
            ventana=self.var_ventana.get(),
            cola=self._cola,
        )
        self.status.config(text=f"Ejecutando simulacion en modo {modo}...")
        self._worker.start()

    def _detener(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            self._worker.detener()
            self.status.config(text="Deteniendo simulacion...")
            self.btn_detener.config(state="disabled")

    def _reset_ui(self) -> None:
        self.tabla.delete(*self.tabla.get_children())
        self.lista_alertas.delete(0, tk.END)
        self._ultimas_alertas.clear()
        self.lbl_contador_alertas.config(text="Alertas activas: 0")
        self.lbl_stats.config(text="Ejecutando...")
        self.progreso.config(maximum=self.var_ciclos.get(), value=0)
        self.lbl_progreso.config(text=f"Ciclo 0 / {self.var_ciclos.get()}")

    # ------------------------------------------------ Bucle de eventos (GUI)
    def _bucle(self) -> None:
        try:
            while True:
                tipo, payload = self._cola.get_nowait()
                if tipo == "evento":
                    self._despachar(payload)
                elif tipo == "error":
                    self._on_error(payload)
                elif tipo == "detenida":
                    self.status.config(text="Simulacion detenida por el usuario.")
                elif tipo == "finished":
                    self._on_worker_finished()
        except queue.Empty:
            pass

        if self._cron_activo:
            elapsed = time.perf_counter() - self._t_inicio
            self.lbl_cron.config(text=f"{elapsed:7.3f} s")

        self.root.after(50, self._bucle)

    def _despachar(self, ev: object) -> None:
        if isinstance(ev, EventoInicio):
            self._on_inicio(ev)
        elif isinstance(ev, EventoEstadoEstacion):
            self._on_estado(ev)
        elif isinstance(ev, EventoMedicion):
            self._on_medicion(ev)
        elif isinstance(ev, EventoAlerta):
            self._on_alerta(ev)
        elif isinstance(ev, EventoCicloFin):
            self._on_ciclo_fin(ev)
        elif isinstance(ev, EventoFinSimulacion):
            self._on_fin(ev)

    # --------------------------------------------------- Handlers de eventos
    def _on_inicio(self, ev: EventoInicio) -> None:
        self.tabla.delete(*self.tabla.get_children())
        for eid, _nombre, zona in ev.estaciones:
            self.tabla.insert(
                "", "end", iid=eid,
                values=(eid, zona, "esperando", "-", "-"),
                tags=("estado_esperando",),
            )
        self.lbl_modo_actual.config(text=f"modo: {ev.modo}")

    def _on_estado(self, ev: EventoEstadoEstacion) -> None:
        if self.tabla.exists(ev.estacion_id):
            self.tabla.set(ev.estacion_id, "estado", ev.estado)
            tag = f"estado_{ev.estado}" if ev.estado in ESTADO_BG else ""
            self.tabla.item(ev.estacion_id, tags=(tag,))

    def _on_medicion(self, ev: EventoMedicion) -> None:
        if self.tabla.exists(ev.estacion_id):
            texto = f"{ev.variable} = {ev.valor:.2f} {VARIABLES[ev.variable].unidad}"
            self.tabla.set(ev.estacion_id, "ultima", texto)
            self.tabla.set(ev.estacion_id, "ciclo", str(ev.ciclo))

    def _on_alerta(self, ev: EventoAlerta) -> None:
        clave = f"{ev.estacion_id}|{ev.ciclo}|{ev.variable}"
        if clave in self._ultimas_alertas:
            return
        self._ultimas_alertas.append(clave)
        texto = (
            f"[ciclo {ev.ciclo}] {ev.zona} - {ev.variable} = {ev.valor:.2f} "
            f"(umbral {ev.umbral:.2f}, sev {ev.severidad:.2f})"
        )
        if ev.severidad >= 0.5:
            color = COLORS["alerta_alta"]
        elif ev.severidad >= 0.2:
            color = COLORS["alerta_media"]
        else:
            color = COLORS["alerta_baja"]
        self.lista_alertas.insert(0, texto)
        self.lista_alertas.itemconfig(0, foreground=color)
        self.lbl_contador_alertas.config(
            text=f"Alertas activas: {self.lista_alertas.size()}"
        )

    def _on_ciclo_fin(self, ev: EventoCicloFin) -> None:
        self.progreso.config(value=ev.ciclo + 1)
        self.lbl_progreso.config(
            text=f"Ciclo {ev.ciclo + 1} / {int(self.progreso['maximum'])}"
        )
        zonas = ", ".join(
            f"{z}={v:.2f}" for z, v in list(ev.indice_zona.items())[:3]
        )
        self.status.config(
            text=(
                f"Ciclo {ev.ciclo + 1}: {ev.mediciones_ciclo} med, "
                f"{ev.alertas_ciclo} alertas, {ev.tiempo_ciclo:.3f}s | {zonas}"
            )
        )

    def _on_fin(self, ev: EventoFinSimulacion) -> None:
        self._cron_activo = False
        indice = "\n".join(
            f"   {z}: {v:.3f}" for z, v in ev.indice_ambiental.items()
        )
        self.lbl_stats.config(
            text=(
                "Simulacion finalizada\n\n"
                f"Tiempo total: {ev.tiempo_total:.3f} s\n"
                f"Mediciones: {ev.total_mediciones}\n"
                f"Mediciones/seg: {ev.mediciones_por_segundo:.2f}\n"
                f"Alertas: {ev.total_alertas}\n"
                f"Zona mayor riesgo: {ev.zona_mayor_riesgo or '-'}\n\n"
                "Indice ambiental por zona:\n"
                f"{indice}"
            )
        )
        self.status.config(
            text=(
                f"Fin. {ev.total_mediciones} mediciones, {ev.total_alertas} alertas "
                f"en {ev.tiempo_total:.3f}s."
            )
        )

    def _on_error(self, msg: str) -> None:
        self.status.config(text=f"Error: {msg}")
        self._cron_activo = False

    def _on_worker_finished(self) -> None:
        self.btn_iniciar.config(state="normal")
        self.btn_detener.config(state="disabled")
        self._cron_activo = False

    # -------------------------------------------------------------- Cierre
    def _al_cerrar(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            self._worker.detener()
            self._worker.join(timeout=2.0)
        self.root.destroy()
