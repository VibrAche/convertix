"""Miniatures des fichiers (photo, 1re image d'une vidéo, 1re page d'un PDF) pour le centre de l'éventail.
Sans Qt (règle du moteur) : renvoie une image Pillow carrée, ou None si le type n'a pas d'aperçu."""
from __future__ import annotations

import io
import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def _square(img, size: int):
    """Recadre au centre en carré (comme une photo de profil) puis réduit."""
    from PIL import ImageOps
    return ImageOps.fit(img.convert("RGBA"), (size, size))


def _image(src: Path, size: int):
    from PIL import Image, ImageOps
    from .converters import images
    ext = src.suffix.lower()
    if ext in images.RAW_EXTS:  # aperçu JPEG intégré au RAW : instantané
        import rawpy
        with rawpy.imread(str(src)) as raw:
            thumb = raw.extract_thumb()
        if thumb.format == rawpy.ThumbFormat.JPEG:
            return ImageOps.exif_transpose(Image.open(io.BytesIO(thumb.data)))
        return Image.fromarray(thumb.data)
    if ext in images.SVG_EXTS:
        return images.load_image(src)[0]
    if ext in images.HEIF_EXTS:
        images._ensure_heif()
    img = Image.open(src)
    img.draft("RGB", (size * 2, size * 2))  # JPEG : décodage réduit, bien plus rapide
    return ImageOps.exif_transpose(img)


def _document(src: Path, size: int):
    from PIL import Image
    from .converters.documents import _fitz
    fitz = _fitz()
    with fitz.open(str(src)) as doc:
        if doc.needs_pass or not doc.page_count:
            return None
        page = doc[0]
        zoom = size * 2 / max(page.rect.width, page.rect.height, 1)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _video(src: Path, size: int):
    from PIL import Image
    from .converters.media import ffmpeg_path
    from .proc import NO_WINDOW
    exe = ffmpeg_path()
    if not exe:
        return None
    for seek in ("1", "0"):  # 1 s après le début (évite l'image noire), sinon tout début pour les vidéos courtes
        res = subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-nostdin", "-ss", seek, "-i", str(src),
                              "-frames:v", "1", "-vf", f"scale={size * 2}:-2", "-f", "image2pipe",
                              "-vcodec", "png", "-"], capture_output=True, timeout=15,
                             stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
        if res.returncode == 0 and res.stdout:
            return Image.open(io.BytesIO(res.stdout))
    return None


def thumbnail(src: Path, size: int = 160):
    """Image Pillow RGBA carrée de `size` px, ou None (pas d'aperçu possible : l'appelant met l'icône du fichier)."""
    from .converters import documents, images, media
    ext = src.suffix.lower()
    try:
        if ext in images.ALL_IMAGE_EXTS | images.SVG_EXTS:
            img = _image(src, size)
        elif ext in documents.PDF_EXTS | documents.EBOOK_EXTS:
            img = _document(src, size)
        elif ext in media.VIDEO_EXTS:
            img = _video(src, size)
        else:
            return None
        return _square(img, size) if img is not None else None
    except Exception as e:
        log.info("Pas de miniature pour %s : %s", src.name, e)
        return None
