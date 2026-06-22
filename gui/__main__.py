# Punto de entrada de la GUI

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from gui.estilo import aplicar_tema
from gui.ventana_principal import VentanaPrincipal


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Monitoreo Ambiental Cuenca")
    aplicar_tema(app)
    ventana = VentanaPrincipal()
    ventana.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
