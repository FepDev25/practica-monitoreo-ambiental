# Estilo visual de la GUI con paleta ambiental y hoja QSS

from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication


# Paleta
COLORS = {
    "bosque": "#2E7D32",
    "bosque_osc": "#1B5E20",
    "hoja": "#66BB6A",
    "rio": "#1565C0",
    "cielo": "#90CAF9",
    "piedra": "#37474F",
    "piedra_clara": "#607D8B",
    "arena": "#ECEFF1",
    "papel": "#FAFAFA",
    "texto": "#1B1B1B",
    "texto_claro": "#ECEFF1",
    "alerta_baja": "#FBC02D",
    "alerta_media": "#FB8C00",
    "alerta_alta": "#C62828",
    "ok": "#43A047",
    "procesando": "#1E88E5",
    "esperando": "#9E9E9E",
    "finalizada": "#6D4C41",
}

# Colores por estado de estacion
ESTADO_BG = {
    "esperando": "#ECEFF1",
    "procesando": "#BBDEFB",
    "activa": "#C8E6C9",
    "finalizada": "#D7CCC8",
}

ESTADO_FG = {
    "esperando": "#37474F",
    "procesando": "#0D47A1",
    "activa": "#1B5E20",
    "finalizada": "#3E2723",
}

# Aplica la paleta ambiental y la hoja QSS a la aplicacion
def aplicar_tema(app: QApplication) -> None:
    app.setStyle("Fusion")
    paleta = QPalette()

    base = QColor(COLORS["papel"])
    texto = QColor(COLORS["texto"])
    bosque = QColor(COLORS["bosque"])
    bosque_osc = QColor(COLORS["bosque_osc"])

    paleta.setColor(QPalette.ColorRole.Window, QColor(COLORS["arena"]))
    paleta.setColor(QPalette.ColorRole.WindowText, texto)
    paleta.setColor(QPalette.ColorRole.Base, base)
    paleta.setColor(QPalette.ColorRole.AlternateBase, QColor("#F1F8E9"))
    paleta.setColor(QPalette.ColorRole.Text, texto)
    paleta.setColor(QPalette.ColorRole.Button, QColor("#E8F5E9"))
    paleta.setColor(QPalette.ColorRole.ButtonText, texto)
    paleta.setColor(QPalette.ColorRole.Highlight, bosque)
    paleta.setColor(QPalette.ColorRole.HighlightedText, QColor(COLORS["texto_claro"]))
    paleta.setColor(QPalette.ColorRole.ToolTipBase, bosque_osc)
    paleta.setColor(QPalette.ColorRole.ToolTipText, QColor(COLORS["texto_claro"]))
    app.setPalette(paleta)

    app.setStyleSheet(_QSS)


_QSS = """
QWidget {
    font-family: 'DejaVu Sans', 'Segoe UI', 'Sans Serif';
    font-size: 10pt;
    color: #1B1B1B;
}
QMainWindow, QWidget#VentanaPrincipal {
    background-color: #ECEFF1;
}
QGroupBox {
    font-weight: bold;
    color: #1B5E20;
    border: 1px solid #C8E6C9;
    border-radius: 6px;
    margin-top: 10px;
    padding: 8px 6px 6px 6px;
    background-color: #FAFAFA;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QPushButton {
    background-color: #2E7D32;
    color: #ECEFF1;
    border: none;
    border-radius: 5px;
    padding: 7px 14px;
    font-weight: bold;
}
QPushButton:hover { background-color: #1B5E20; }
QPushButton:pressed { background-color: #0F3D14; }
QPushButton:disabled { background-color: #A5D6A7; color: #ECEFF1; }
QPushButton#btnDetener {
    background-color: #C62828;
}
QPushButton#btnDetener:hover { background-color: #B71C1C; }
QComboBox, QSpinBox {
    background-color: #FAFAFA;
    border: 1px solid #90CAF9;
    border-radius: 4px;
    padding: 4px 6px;
}
QComboBox:hover, QSpinBox:hover { border: 1px solid #1565C0; }
QTableWidget {
    background-color: #FAFAFA;
    alternate-background-color: #F1F8E9;
    border: 1px solid #C8E6C9;
    border-radius: 4px;
    gridline-color: #E8F5E9;
    selection-background-color: #66BB6A;
    selection-color: #1B1B1B;
}
QHeaderView::section {
    background-color: #2E7D32;
    color: #ECEFF1;
    padding: 5px;
    border: none;
    font-weight: bold;
}
QListWidget {
    background-color: #FFFDE7;
    border: 1px solid #FFE082;
    border-radius: 4px;
}
QListWidget::item {
    border-bottom: 1px solid #FFF9C4;
    padding: 3px;
}
QLabel#lblTitulo {
    font-size: 15pt;
    font-weight: bold;
    color: #1B5E20;
}
QLabel#lblSubtitulo {
    font-size: 9pt;
    color: #607D8B;
}
QLabel#lblModo {
    font-size: 11pt;
    font-weight: bold;
    color: #1565C0;
}
QLabel#lblCronometro {
    font-family: 'DejaVu Sans Mono', monospace;
    font-size: 14pt;
    font-weight: bold;
    color: #1B5E20;
}
QStatusBar {
    background-color: #37474F;
    color: #ECEFF1;
}
QProgressBar {
    border: 1px solid #C8E6C9;
    border-radius: 4px;
    text-align: center;
    background-color: #E8F5E9;
}
QProgressBar::chunk {
    background-color: #66BB6A;
    border-radius: 3px;
}
QTabWidget::pane {
    border: 1px solid #C8E6C9;
    border-radius: 4px;
    background-color: #FAFAFA;
}
QTabBar::tab {
    background-color: #E8F5E9;
    color: #1B5E20;
    padding: 6px 12px;
    border: 1px solid #C8E6C9;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background-color: #2E7D32;
    color: #ECEFF1;
}
QScrollBar:vertical {
    background: #ECEFF1;
    width: 10px;
    border: none;
}
QScrollBar::handle:vertical {
    background: #66BB6A;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #2E7D32; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
