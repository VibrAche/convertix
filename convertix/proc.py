"""Lancement de programmes externes (ffmpeg, LibreOffice) sans fenêtre console et annulable."""
from __future__ import annotations

import collections
import subprocess
import sys
import threading
import time
from typing import Callable

from .engine import Cancelled, ConversionError, ConvertOptions

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW


def run(cmd: list[str], opts: ConvertOptions, timeout: float = 3600, what: str = "",
        on_line: Callable[[str], None] | None = None) -> str:
    """Exécute `cmd`, renvoie la fin de stderr+stdout. Lève Cancelled si l'utilisateur annule.
    `on_line` reçoit chaque ligne au fil de l'eau (ex. avancement de ffmpeg)."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
    lines: collections.deque[str] = collections.deque(maxlen=400)

    def read() -> None:
        for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            lines.append(line)
            if on_line:
                try:
                    on_line(line)
                except Exception:
                    pass

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    start = time.monotonic()
    try:
        while proc.poll() is None:
            time.sleep(0.2)
            if opts.cancel.is_set():
                proc.kill()
                raise Cancelled()
            if time.monotonic() - start > timeout:
                proc.kill()
                raise ConversionError(f"{what or cmd[0]} : délai dépassé")
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        reader.join(timeout=5)
    text = "\n".join(lines)
    if proc.returncode != 0:
        tail = "\n".join(line for line in lines if line and "=" not in line[:20])
        tail = "\n".join(tail.strip().splitlines()[-4:])
        raise ConversionError(f"{what or cmd[0]} a échoué (code {proc.returncode}).\n{tail}")
    return text
