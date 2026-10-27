"""Lancement de programmes externes (ffmpeg, LibreOffice) sans fenêtre console et annulable."""
from __future__ import annotations

import subprocess
import sys
import time

from .engine import Cancelled, ConversionError, ConvertOptions

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW


def run(cmd: list[str], opts: ConvertOptions, timeout: float = 3600, what: str = "") -> str:
    """Exécute `cmd`, renvoie stderr+stdout. Lève Cancelled si l'utilisateur annule."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
    start = time.monotonic()
    try:
        while True:
            try:
                out, _ = proc.communicate(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                if opts.cancel.is_set():
                    proc.kill()
                    proc.communicate()
                    raise Cancelled()
                if time.monotonic() - start > timeout:
                    proc.kill()
                    proc.communicate()
                    raise ConversionError(f"{what or cmd[0]} : délai dépassé")
    finally:
        if proc.poll() is None:
            proc.kill()
    text = out.decode("utf-8", errors="replace") if out else ""
    if proc.returncode != 0:
        tail = "\n".join(text.strip().splitlines()[-4:])
        raise ConversionError(f"{what or cmd[0]} a échoué (code {proc.returncode}).\n{tail}")
    return text
