"""Thread de conversion : ne bloque jamais l'interface."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .. import engine
from ..engine import Cancelled, ConversionError, ConvertOptions

log = logging.getLogger(__name__)


class ConvertWorker(QThread):
    progress = Signal(int, int, str)          # index, total, nom du fichier
    done = Signal(list, list, bool)           # fichiers produits, erreurs, annulé ?

    def __init__(self, files: list[Path], key: str, opts: ConvertOptions, merge: bool):
        super().__init__()
        self.files, self.key, self.opts, self.merge = files, key, opts, merge

    def cancel(self) -> None:
        self.opts.cancel.set()

    def run(self) -> None:
        produced: list[Path] = []
        errors: list[str] = []
        cancelled = False
        try:
            if self.merge:
                self.progress.emit(0, 1, f"Fusion de {len(self.files)} fichiers")
                produced.append(engine.merge_to_pdf(self.files, self.opts))
            else:
                todo = [f for f in self.files if engine.can_convert(f, self.key)]
                skipped = [f for f in self.files if f not in todo]
                errors += [f"{f.name} : ce type de fichier ne peut pas être converti en {self.key.upper()}"
                           for f in skipped]
                for i, f in enumerate(todo):
                    self.progress.emit(i, len(todo), f.name)
                    try:
                        produced += engine.convert(f, self.key, self.opts)
                    except Cancelled:
                        raise
                    except ConversionError as e:
                        errors.append(str(e))
                    except Exception as e:  # sécurité : ne jamais planter le thread
                        log.exception("Erreur inattendue")
                        errors.append(f"{f.name} : {e}")
        except Cancelled:
            cancelled = True
        except Exception as e:
            log.exception("Erreur de conversion")
            errors.append(str(e))
        self.done.emit(produced, errors, cancelled)
