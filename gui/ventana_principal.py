# Ventana principal de la GUI del sistema de monitoreo ambiental

from __future__ import annotations

import time
from collections import deque

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

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


class VentanaPrincipal(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Monitoreo Ambiental Urbano - Cuenca")
        self.resize(1200, 760)
        self.setMinimumSize(960, 600)

        self._worker: WorkerSimulacion | None = None
        self._controladores = descubrir_controladores()
        self._t_inicio: float = 0.0
        self._cron_activo = False
        self._ultimas_alertas: deque[str] = deque(maxlen=200)

        self._construir_ui()
        self._poblar_entorno()
        self._cron_timer = QTimer(self)
        self._cron_timer.setInterval(100)
        self._cron_timer.timeout.connect(self._tick_cronometro)

    # Construccion de la UI
    def _construir_ui(self) -> None:
        central = QWidget()
        central.setObjectName("VentanaPrincipal")
        self.setCentralWidget(central)
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(10, 10, 10, 10)
        raiz.setSpacing(8)

        # Cabecera
        titulo = QLabel("Sistema de Monitoreo Ambiental Urbano - Cuenca")
        titulo.setObjectName("lblTitulo")
        sub = QLabel("Simulacion de estaciones con paralelismo: secuencial / hilos / procesos")
        sub.setObjectName("lblSubtitulo")
        raiz.addWidget(titulo)
        raiz.addWidget(sub)

        raiz.addWidget(self._panel_controles())
        raiz.addWidget(self._panel_principal(), 1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Listo.")

    def _panel_controles(self) -> QWidget:
        grupo = QGroupBox("Configuracion de la simulacion")
        layout = QHBoxLayout(grupo)
        layout.setSpacing(10)

        self.cb_modo = QComboBox()
        for modo in ("secuencial", "hilos", "procesos"):
            if modo in self._controladores:
                self.cb_modo.addItem(modo)
        self.cb_modo.setCurrentText("secuencial")
        self.cb_modo.currentTextChanged.connect(self._cambio_modo)
        layout.addWidget(QLabel("Modo:"))
        layout.addWidget(self.cb_modo)

        self.sb_estaciones = QSpinBox()
        self.sb_estaciones.setRange(1, 24)
        self.sb_estaciones.setValue(4)
        layout.addWidget(QLabel("Estaciones:"))
        layout.addWidget(self.sb_estaciones)

        self.sb_ciclos = QSpinBox()
        self.sb_ciclos.setRange(1, 200)
        self.sb_ciclos.setValue(10)
        layout.addWidget(QLabel("Ciclos:"))
        layout.addWidget(self.sb_ciclos)

        self.sb_intensidad = QSpinBox()
        self.sb_intensidad.setRange(1, 20000)
        self.sb_intensidad.setSingleStep(100)
        self.sb_intensidad.setValue(2000)
        layout.addWidget(QLabel("Intensidad CPU:"))
        layout.addWidget(self.sb_intensidad)

        self.sb_ventana = QSpinBox()
        self.sb_ventana.setRange(1, 100)
        self.sb_ventana.setValue(10)
        layout.addWidget(QLabel("Ventana MM:"))
        layout.addWidget(self.sb_ventana)

        layout.addStretch(1)

        self.lbl_modo_actual = QLabel("modo: secuencial")
        self.lbl_modo_actual.setObjectName("lblModo")
        layout.addWidget(self.lbl_modo_actual)

        self.btn_iniciar = QPushButton("Iniciar")
        self.btn_iniciar.clicked.connect(self._iniciar)
        self.btn_detener = QPushButton("Detener")
        self.btn_detener.setObjectName("btnDetener")
        self.btn_detener.clicked.connect(self._detener)
        self.btn_detener.setEnabled(False)
        layout.addWidget(self.btn_iniciar)
        layout.addWidget(self.btn_detener)
        return grupo

    def _panel_principal(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Izquierda: estaciones
        izq = QGroupBox("Estaciones ambientales")
        izq_l = QVBoxLayout(izq)
        self.tabla_estaciones = QTableWidget(0, 5)
        self.tabla_estaciones.setHorizontalHeaderLabels(
            ["ID", "Zona", "Estado", "Ultima medicion", "Ciclo"]
        )
        self.tabla_estaciones.horizontalHeader().setStretchLastSection(False)
        self.tabla_estaciones.horizontalHeader().setSectionResizeMode(
            3, self.tabla_estaciones.horizontalHeader().ResizeMode.Stretch
        )
        self.tabla_estaciones.setAlternatingRowColors(True)
        self.tabla_estaciones.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        izq_l.addWidget(self.tabla_estaciones)

        self.progreso = QProgressBar()
        self.progreso.setRange(0, 100)
        self.progreso.setValue(0)
        self.progreso.setFormat("Ciclo %v / %m")
        izq_l.addWidget(self.progreso)

        # Derecha: alertas + estadisticas (tabs)
        der = QGroupBox("Resultados en vivo")
        der_l = QVBoxLayout(der)
        tabs = QTabWidget()

        tab_alertas = QWidget()
        ta_l = QVBoxLayout(tab_alertas)
        self.lista_alertas = QListWidget()
        self.lista_alertas.setWordWrap(True)
        ta_l.addWidget(self.lista_alertas)
        self.lbl_contador_alertas = QLabel("Alertas activas: 0")
        ta_l.addWidget(self.lbl_contador_alertas)
        tabs.addTab(tab_alertas, "Alertas")

        tab_stats = QWidget()
        ts_l = QVBoxLayout(tab_stats)
        self.lbl_stats = QLabel("Sin datos aun. Ejecute una simulacion.")
        self.lbl_stats.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.lbl_stats.setWordWrap(True)
        ts_l.addWidget(self.lbl_stats)
        tabs.addTab(tab_stats, "Estadisticas")

        tab_entorno = QWidget()
        te_l = QFormLayout(tab_entorno)
        te_l.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbls_entorno: dict[str, QLabel] = {}
        for clave in (
            "python", "implementacion", "sistema", "release",
            "maquina", "cpu_count", "gil_habilitado", "build_free_threading",
        ):
            lbl = QLabel("-")
            te_l.addRow(clave.replace("_", " ").capitalize(), lbl)
            self.lbls_entorno[clave] = lbl
        tabs.addTab(tab_entorno, "Entorno")

        der_l.addWidget(tabs)
        splitter.addWidget(izq)
        splitter.addWidget(der)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        return splitter

    # Entorno
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
            lbl.setText(textos.get(clave, "-"))

    # Controles
    def _cambio_modo(self, modo: str) -> None:
        self.lbl_modo_actual.setText(f"modo: {modo}")

    def _iniciar(self) -> None:
        modo = self.cb_modo.currentText()
        clase = self._controladores.get(modo)
        if clase is None:
            self.status.showMessage(f"Modo {modo!r} no disponible.")
            return
        self._reset_ui()
        self.btn_iniciar.setEnabled(False)
        self.btn_detener.setEnabled(True)
        self._t_inicio = time.perf_counter()
        self._cron_activo = True
        self._cron_timer.start()

        self._worker = WorkerSimulacion(
            clase_controlador=clase,
            num_estaciones=self.sb_estaciones.value(),
            num_ciclos=self.sb_ciclos.value(),
            intensidad=self.sb_intensidad.value(),
            ventana=self.sb_ventana.value(),
        )
        self._worker.inicio.connect(self._on_inicio)
        self._worker.estado_estacion.connect(self._on_estado)
        self._worker.medicion.connect(self._on_medicion)
        self._worker.alerta.connect(self._on_alerta)
        self._worker.ciclo_fin.connect(self._on_ciclo_fin)
        self._worker.fin_simulacion.connect(self._on_fin)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)
        self.status.showMessage(f"Ejecutando simulacion en modo {modo}...")
        self._worker.start()

    def _detener(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.detener()
            self.status.showMessage("Deteniendo simulacion...")
            self.btn_detener.setEnabled(False)

    def _reset_ui(self) -> None:
        self.tabla_estaciones.setRowCount(0)
        self.lista_alertas.clear()
        self._ultimas_alertas.clear()
        self.lbl_contador_alertas.setText("Alertas activas: 0")
        self.lbl_stats.setText("Ejecutando...")
        self.progreso.setRange(0, self.sb_ciclos.value())
        self.progreso.setValue(0)

    # Handlers de eventos (se ejecutan en el hilo de la GUI)
    def _on_inicio(self, ev: EventoInicio) -> None:
        self.tabla_estaciones.setRowCount(len(ev.estaciones))
        for i, (eid, nombre, zona) in enumerate(ev.estaciones):
            self.tabla_estaciones.setItem(i, 0, QTableWidgetItem(eid))
            self.tabla_estaciones.setItem(i, 1, QTableWidgetItem(zona))
            self._set_estado_fila(i, "esperando", 0)
            self.tabla_estaciones.setItem(i, 3, QTableWidgetItem("-"))
            self.tabla_estaciones.setItem(i, 4, QTableWidgetItem("-"))
        self.lbl_modo_actual.setText(f"modo: {ev.modo}")

    def _on_estado(self, ev: EventoEstadoEstacion) -> None:
        fila = self._buscar_fila(ev.estacion_id)
        if fila is not None:
            self._set_estado_fila(fila, ev.estado, ev.ciclo)

    def _on_medicion(self, ev: EventoMedicion) -> None:
        fila = self._buscar_fila(ev.estacion_id)
        if fila is not None:
            texto = f"{ev.variable} = {ev.valor:.2f} {VARIABLES[ev.variable].unidad}"
            self.tabla_estaciones.setItem(fila, 3, QTableWidgetItem(texto))
            self.tabla_estaciones.setItem(fila, 4, QTableWidgetItem(str(ev.ciclo)))

    def _on_alerta(self, ev: EventoAlerta) -> None:
        clave = f"{ev.estacion_id}|{ev.ciclo}|{ev.variable}"
        if clave in self._ultimas_alertas:
            return
        self._ultimas_alertas.append(clave)
        texto = (
            f"[ciclo {ev.ciclo}] {ev.zona} - {ev.variable} = {ev.valor:.2f} "
            f"(umbral {ev.umbral:.2f}, sev {ev.severidad:.2f})"
        )
        item = QListWidgetItem(texto)
        if ev.severidad >= 0.5:
            color = QColor(COLORS["alerta_alta"])
        elif ev.severidad >= 0.2:
            color = QColor(COLORS["alerta_media"])
        else:
            color = QColor(COLORS["alerta_baja"])
        item.setForeground(color)
        self.lista_alertas.insertItem(0, item)
        self.lbl_contador_alertas.setText(
            f"Alertas activas: {self.lista_alertas.count()}"
        )

    def _on_ciclo_fin(self, ev: EventoCicloFin) -> None:
        self.progreso.setValue(ev.ciclo + 1)
        zonas = ", ".join(
            f"{z}={v:.2f}" for z, v in list(ev.indice_zona.items())[:3]
        )
        self.status.showMessage(
            f"Ciclo {ev.ciclo + 1}: {ev.mediciones_ciclo} med, "
            f"{ev.alertas_ciclo} alertas, {ev.tiempo_ciclo:.3f}s | {zonas}"
        )

    def _on_fin(self, ev: EventoFinSimulacion) -> None:
        self._cron_activo = False
        self._cron_timer.stop()
        self.lbl_stats.setText(
            f"<b>Simulacion finalizada</b><br>"
            f"Tiempo total: <b>{ev.tiempo_total:.3f} s</b><br>"
            f"Mediciones: {ev.total_mediciones}<br>"
            f"Mediciones/seg: {ev.mediciones_por_segundo:.2f}<br>"
            f"Alertas: {ev.total_alertas}<br>"
            f"Zona mayor riesgo: <b>{ev.zona_mayor_riesgo or '-'}</b><br><br>"
            f"<b>Indice ambiental por zona:</b><br>"
            + "<br>".join(
                f"{z}: {v:.3f}" for z, v in ev.indice_ambiental.items()
            )
        )
        self.status.showMessage(
            f"Fin. {ev.total_mediciones} mediciones, {ev.total_alertas} alertas "
            f"en {ev.tiempo_total:.3f}s."
        )

    def _on_error(self, msg: str) -> None:
        self.status.showMessage(f"Error: {msg}")
        self._cron_activo = False
        self._cron_timer.stop()

    def _on_worker_finished(self) -> None:
        self.btn_iniciar.setEnabled(True)
        self.btn_detener.setEnabled(False)
        self._cron_activo = False
        self._cron_timer.stop()

    # Cronometro
    def _tick_cronometro(self) -> None:
        if not self._cron_activo:
            return
        elapsed = time.perf_counter() - self._t_inicio
        self.status.showMessage(f"Tiempo: {elapsed:7.3f} s")

    # Helpers
    def _buscar_fila(self, estacion_id: str) -> int | None:
        for i in range(self.tabla_estaciones.rowCount()):
            it = self.tabla_estaciones.item(i, 0)
            if it is not None and it.text() == estacion_id:
                return i
        return None

    def _set_estado_fila(self, fila: int, estado: str, ciclo: int) -> None:
        item = QTableWidgetItem(estado)
        item.setForeground(QColor(ESTADO_FG.get(estado, "#1B1B1B")))
        self.tabla_estaciones.setItem(fila, 2, item)
        # color de fondo de toda la fila
        bg = QColor(ESTADO_BG.get(estado, "#FAFAFA"))
        for col in range(self.tabla_estaciones.columnCount()):
            celda = self.tabla_estaciones.item(fila, col)
            if celda is None:
                celda = QTableWidgetItem("")
                self.tabla_estaciones.setItem(fila, col, celda)
            celda.setBackground(bg)
