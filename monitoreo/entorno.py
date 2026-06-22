# Informacion del entorno de ejecucion
from __future__ import annotations

import os
import platform
import sys
import sysconfig

# devuelve el estado del GIL si la version de Python lo permite
def gil_habilitado() -> bool | None:
    funcion = getattr(sys, "_is_gil_enabled", None)
    if callable(funcion):
        try:
            return bool(funcion())
        except Exception:
            return None
    return None

# reune la informacion del entorno en un diccionario plano
def info_entorno() -> dict:
    return {
        "python": platform.python_version(),
        "implementacion": platform.python_implementation(),
        "build_free_threading": (
            sysconfig.get_config_var("Py_GIL_DISABLED") == 1
        ),
        "sistema": platform.system(),
        "release": platform.release(),
        "maquina": platform.machine(),
        "cpu_count": os.cpu_count(),
        "gil_habilitado": gil_habilitado(),
    }

# version en texto plano para mostrar en consola, GUI o informe
def resumen_entorno() -> str:
    e = info_entorno()
    gil = (
        "si" if e["gil_habilitado"] is True
        else "no" if e["gil_habilitado"] is False
        else "no determinable"
    )
    return (
        f"Python {e['python']} ({e['implementacion']}) | "
        f"{e['sistema']} {e['release']} {e['maquina']} | "
        f"nucleos={e['cpu_count']} | GIL={gil}"
    )
