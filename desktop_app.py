"""
Version de escritorio de Manager Tapper.

Corre el mismo backend Flask (app.py) en un hilo de fondo y lo muestra en una
ventana nativa de Windows usando pywebview, en vez de un navegador. Es el
mismo codigo que la version web -- esto es solo el "empaque".

Para generar el .exe, ver las instrucciones en README.md.
"""
import os
import threading
import time
from pathlib import Path

import webview


def _data_dir() -> Path:
    """Carpeta en el perfil del usuario donde se guarda la base de datos."""
    base = Path(os.path.expanduser("~")) / "ManagerTapper"
    base.mkdir(parents=True, exist_ok=True)
    return base


# Debe definirse ANTES de importar app.py, para que create_app() lo use.
os.environ["MANAGER_TAPPER_DB"] = (_data_dir() / "manager_tapper.db").as_posix()

from app import app  # noqa: E402  (import tardío a propósito, ver arriba)

HOST = "127.0.0.1"
PORT = 5000


def iniciar_servidor():
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


def main():
    hilo = threading.Thread(target=iniciar_servidor, daemon=True)
    hilo.start()
    time.sleep(1)  # da tiempo a que Flask arranque antes de abrir la ventana

    webview.create_window(
        "Manager Tapper",
        f"http://{HOST}:{PORT}",
        width=1000,
        height=750,
        min_size=(700, 500),
    )
    webview.start()


if __name__ == "__main__":
    main()
