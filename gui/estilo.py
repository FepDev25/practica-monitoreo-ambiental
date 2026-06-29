# Estilo visual de la GUI con paleta ambiental (tkinter / ttk)

from __future__ import annotations

from tkinter import ttk

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

# Colores de fondo por estado de estacion (fila de la tabla)
ESTADO_BG = {
    "esperando": "#ECEFF1",
    "procesando": "#BBDEFB",
    "activa": "#C8E6C9",
    "finalizada": "#D7CCC8",
}

# Colores de texto por estado de estacion
ESTADO_FG = {
    "esperando": "#37474F",
    "procesando": "#0D47A1",
    "activa": "#1B5E20",
    "finalizada": "#3E2723",
}

FUENTE = ("DejaVu Sans", 10)
FUENTE_BOLD = ("DejaVu Sans", 10, "bold")
FUENTE_MONO = ("DejaVu Sans Mono", 13, "bold")


# Aplica la paleta ambiental y los estilos ttk a la ventana raiz.
# Sustituye a la hoja QSS de la version PyQt6.
def aplicar_tema(root) -> None:
    root.configure(bg=COLORS["arena"])

    style = ttk.Style(root)
    style.theme_use("clam")

    # Base
    style.configure(
        ".",
        font=FUENTE,
        background=COLORS["arena"],
        foreground=COLORS["texto"],
    )
    style.configure("TFrame", background=COLORS["arena"])
    style.configure("TLabel", background=COLORS["arena"], foreground=COLORS["texto"])

    # Grupos (LabelFrame)
    style.configure(
        "TLabelframe",
        background=COLORS["papel"],
        bordercolor=COLORS["hoja"],
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        "TLabelframe.Label",
        background=COLORS["arena"],
        foreground=COLORS["bosque_osc"],
        font=FUENTE_BOLD,
    )

    # Etiquetas especiales
    style.configure(
        "Titulo.TLabel",
        font=("DejaVu Sans", 15, "bold"),
        foreground=COLORS["bosque_osc"],
    )
    style.configure(
        "Subtitulo.TLabel",
        font=("DejaVu Sans", 9),
        foreground=COLORS["piedra_clara"],
    )
    style.configure(
        "Modo.TLabel",
        font=("DejaVu Sans", 11, "bold"),
        foreground=COLORS["rio"],
    )
    style.configure(
        "Cron.TLabel",
        font=FUENTE_MONO,
        foreground=COLORS["bosque_osc"],
    )
    style.configure(
        "Estado.TLabel",
        background=COLORS["piedra"],
        foreground=COLORS["texto_claro"],
    )

    # Botones
    style.configure(
        "TButton",
        font=FUENTE_BOLD,
        padding=(12, 6),
        borderwidth=0,
    )
    style.configure(
        "Iniciar.TButton",
        background=COLORS["bosque"],
        foreground=COLORS["texto_claro"],
    )
    style.map(
        "Iniciar.TButton",
        background=[("active", COLORS["bosque_osc"]), ("disabled", "#A5D6A7")],
        foreground=[("disabled", COLORS["texto_claro"])],
    )
    style.configure(
        "Detener.TButton",
        background=COLORS["alerta_alta"],
        foreground=COLORS["texto_claro"],
    )
    style.map(
        "Detener.TButton",
        background=[("active", "#B71C1C"), ("disabled", "#EF9A9A")],
        foreground=[("disabled", COLORS["texto_claro"])],
    )

    # Entradas
    style.configure(
        "TCombobox",
        fieldbackground=COLORS["papel"],
        background=COLORS["papel"],
        bordercolor=COLORS["cielo"],
        padding=3,
    )
    style.configure(
        "TSpinbox",
        fieldbackground=COLORS["papel"],
        bordercolor=COLORS["cielo"],
        padding=3,
    )

    # Tabla (Treeview)
    style.configure(
        "Treeview",
        background=COLORS["papel"],
        fieldbackground=COLORS["papel"],
        foreground=COLORS["texto"],
        rowheight=26,
        borderwidth=1,
    )
    style.configure(
        "Treeview.Heading",
        background=COLORS["bosque"],
        foreground=COLORS["texto_claro"],
        font=FUENTE_BOLD,
        relief="flat",
    )
    style.map(
        "Treeview.Heading",
        background=[("active", COLORS["bosque_osc"])],
    )
    style.map(
        "Treeview",
        background=[("selected", COLORS["hoja"])],
        foreground=[("selected", COLORS["texto"])],
    )

    # Barra de progreso
    style.configure(
        "TProgressbar",
        troughcolor="#E8F5E9",
        background=COLORS["hoja"],
        bordercolor=COLORS["hoja"],
    )

    # Pestañas (Notebook)
    style.configure("TNotebook", background=COLORS["arena"], borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        background="#E8F5E9",
        foreground=COLORS["bosque_osc"],
        padding=(12, 6),
        font=FUENTE_BOLD,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", COLORS["bosque"])],
        foreground=[("selected", COLORS["texto_claro"])],
    )
