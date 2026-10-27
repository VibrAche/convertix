"""Moteur de conversion : registre des règles « extension d'entrée → format de sortie ».

Chaque module de `convertix.converters` enregistre ses règles via `register(registry)`.
L'interface (dialogue, CLI) ne parle qu'à ce module :

    targets_for(paths)        → formats proposés pour une sélection
    convert(path, key, opts)  → liste des fichiers produits
    merge_to_pdf(paths, opts) → un seul PDF à partir d'images / PDF
"""
from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

log = logging.getLogger(__name__)


class ConversionError(Exception):
    """Erreur affichable à l'utilisateur (message en français)."""


class Cancelled(Exception):
    pass


@dataclass(frozen=True)
class Target:
    key: str    # identifiant stable, ex. "jpg"
    label: str  # libellé affiché, ex. "JPEG"
    ext: str    # extension produite, ex. ".jpg"
    group: str  # "Image", "Document", "Tableur", "Présentation", "Vidéo", "Audio"


@dataclass
class ConvertOptions:
    quality: int = 92
    keep_metadata: bool = True
    output_dir: Path | None = None  # None → même dossier que la source
    subfolder: str | None = None    # ex. "Convertis" → <dossier source>/Convertis
    cancel: threading.Event = field(default_factory=threading.Event)
    progress: Callable[[float], None] | None = None  # avancement du fichier en cours (0 → 1), si connu

    def check_cancel(self) -> None:
        if self.cancel.is_set():
            raise Cancelled()

    def report(self, fraction: float) -> None:
        if self.progress is not None:
            try:
                self.progress(max(0.0, min(1.0, fraction)))
            except Exception:
                pass


class Output:
    """Calcule des chemins de sortie sans jamais écraser un fichier existant."""

    def __init__(self, src: Path, opts: ConvertOptions):
        self.src = src
        if opts.output_dir:
            self.dir = Path(opts.output_dir)
        elif opts.subfolder:
            self.dir = src.parent / opts.subfolder
        else:
            self.dir = src.parent
        self.dir.mkdir(parents=True, exist_ok=True)

    def file(self, ext: str, stem: str | None = None) -> Path:
        return unique_path(self.dir / f"{stem or self.src.stem}{ext}")

    def folder(self, suffix: str = " - pages") -> Path:
        p = unique_path(self.dir / f"{self.src.stem}{suffix}")
        p.mkdir(parents=True)
        return p


def unique_path(p: Path) -> Path:
    """`photo.jpg` → `photo (1).jpg` si le fichier existe déjà."""
    if not p.exists():
        return p
    i = 1
    while True:
        cand = p.with_name(f"{p.stem} ({i}){p.suffix}")
        if not cand.exists():
            return cand
        i += 1


ConvertFunc = Callable[[Path, Target, Output, ConvertOptions], list[Path]]


@dataclass
class Rule:
    inputs: frozenset[str]   # extensions en minuscules avec le point
    target: Target
    func: ConvertFunc
    available: Callable[[], bool] = lambda: True
    priority: int = 0        # en cas de doublon, la règle disponible la plus prioritaire gagne


class Registry:
    def __init__(self) -> None:
        self.rules: list[Rule] = []
        self.targets: dict[str, Target] = {}

    def add(self, inputs: Iterable[str], target: Target, func: ConvertFunc,
            available: Callable[[], bool] | None = None, priority: int = 0) -> None:
        self.targets.setdefault(target.key, target)
        self.rules.append(Rule(frozenset(e.lower() for e in inputs), target, func,
                               available or (lambda: True), priority))

    def rule_for(self, ext: str, key: str) -> Rule | None:
        cands = [r for r in self.rules if r.target.key == key and ext in r.inputs]
        cands.sort(key=lambda r: -r.priority)
        for r in cands:
            try:
                if r.available():
                    return r
            except Exception:
                log.exception("Test de disponibilité en échec pour %s", key)
        return None

    def targets_for_ext(self, ext: str) -> list[Target]:
        seen: OrderedDict[str, Target] = OrderedDict()
        for r in self.rules:
            if ext in r.inputs and r.target.key not in seen and self.rule_for(ext, r.target.key):
                seen[r.target.key] = r.target
        return list(seen.values())

    def supported_inputs(self) -> set[str]:
        return {e for r in self.rules for e in r.inputs}


_registry: Registry | None = None


def registry() -> Registry:
    global _registry
    if _registry is None:
        reg = Registry()
        from .converters import documents, images, media  # import tardif (démarrage rapide)
        images.register(reg)
        documents.register(reg)
        media.register(reg)
        _registry = reg
    return _registry


def ext_of(p: Path) -> str:
    return p.suffix.lower()


SKIP_DIRS = {"Convertis"}  # dossiers de sortie : jamais reconvertis lors d'un traitement par lot


def _skipped(f: Path, root: Path) -> bool:
    parts = f.relative_to(root).parts[:-1]
    return any(p in SKIP_DIRS or p.endswith(" - pages") or p.startswith(".") for p in parts)


MAX_FILES = 5000  # garde-fou : un dossier énorme ne doit pas bloquer l'interface


def collect_files(paths: Iterable[Path | str], recursive: bool = True) -> list[Path]:
    """Développe les dossiers en fichiers convertibles (traitement par lot), sans doublons."""
    supported = registry().supported_inputs()
    seen: dict[str, Path] = {}
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            if p.anchor and Path(p.anchor) == p:  # racine d'un disque (C:\) : refusé
                log.warning("Racine de disque ignorée : %s", p)
                continue
            it = p.rglob("*") if recursive else p.iterdir()
            for f in sorted(it):
                if len(seen) >= MAX_FILES:
                    log.warning("Plus de %d fichiers : liste tronquée", MAX_FILES)
                    break
                if f.is_file() and ext_of(f) in supported and not f.name.startswith(".") and not _skipped(f, p):
                    seen.setdefault(str(f.resolve()).lower(), f)
        elif p.is_file():
            seen.setdefault(str(p.resolve()).lower(), p)
    return list(seen.values())


def targets_for(paths: Iterable[Path]) -> list[tuple[Target, int]]:
    """Formats proposés pour la sélection + nombre de fichiers compatibles pour chacun.

    Le format d'origine d'un fichier n'est pas proposé pour ce fichier
    (sauf réencodage vidéo/audio utile, ex. MP4 → MP4 compressé : non géré en v1).
    """
    reg = registry()
    counts: OrderedDict[str, int] = OrderedDict()
    first: dict[str, Target] = {}
    for p in paths:
        ext = ext_of(p)
        for t in reg.targets_for_ext(ext):
            if t.ext == ext or (t.key == "jpg" and ext in (".jpeg", ".jpe", ".jfif")) or (t.key == "tiff" and ext == ".tif"):
                continue
            counts[t.key] = counts.get(t.key, 0) + 1
            first.setdefault(t.key, t)
    return [(first[k], n) for k, n in counts.items()]


def can_convert(path: Path, key: str) -> bool:
    return registry().rule_for(ext_of(path), key) is not None


def convert(path: Path, key: str, opts: ConvertOptions | None = None) -> list[Path]:
    opts = opts or ConvertOptions()
    path = Path(path)
    if not path.is_file():
        raise ConversionError(f"Fichier introuvable : {path}")
    rule = registry().rule_for(ext_of(path), key)
    if rule is None:
        raise ConversionError(f"Conversion {path.suffix or '?'} → {key.upper()} non prise en charge.")
    opts.check_cancel()
    log.info("Conversion %s → %s", path, key)
    out = Output(path, opts)
    try:
        results = rule.func(path, rule.target, out, opts)
    except (ConversionError, Cancelled):
        raise
    except Exception as e:  # on transforme toute erreur technique en message lisible
        log.exception("Échec de conversion %s → %s", path, key)
        raise ConversionError(f"{path.name} : {e}") from e
    log.info("→ %s", ", ".join(str(r) for r in results))
    return results


def merge_to_pdf(paths: list[Path], opts: ConvertOptions | None = None) -> Path:
    from .converters.documents import merge_to_pdf as _merge
    return _merge([Path(p) for p in paths], opts or ConvertOptions())


def mergeable(paths: Iterable[Path]) -> list[Path]:
    from .converters.documents import MERGEABLE
    return [Path(p) for p in paths if ext_of(Path(p)) in MERGEABLE]
