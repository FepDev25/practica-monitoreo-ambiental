# Punto de entrada de la GUI

from __future__ import annotations

import tkinter as tk

from gui.estilo import aplicar_tema
from gui.ventana_principal import VentanaPrincipal


def main() -> None:
    root = tk.Tk()
    aplicar_tema(root)
    VentanaPrincipal(root)
    root.mainloop()


if __name__ == "__main__":
    main()
