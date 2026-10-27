"""Conversions d'images : RAW (DNG iPhone, CR2, NEF…), HEIC/HEIF, AVIF et formats classiques."""
from __future__ import annotations

import io
import logging
from pathlib import Path

from ..engine import ConversionError, ConvertOptions, Output, Registry, Target

log = logging.getLogger(__name__)

RAW_EXTS = {".dng", ".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".raf", ".orf",
            ".rw2", ".pef", ".srw", ".raw", ".3fr", ".erf", ".kdc", ".mrw", ".x3f", ".iiq"}
HEIF_EXTS = {".heic", ".heif", ".hif"}
STD_EXTS = {".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".webp", ".tif", ".tiff", ".bmp",
            ".gif", ".ico", ".avif", ".tga", ".ppm", ".psd"}
ALL_IMAGE_EXTS = RAW_EXTS | HEIF_EXTS | STD_EXTS
SVG_EXTS = {".svg"}  # vectoriel : rendu par PyMuPDF (hors ALL_IMAGE_EXTS, que la fusion PDF ouvre avec Pillow)
SVG_SIDE = 2048      # côté le plus long du rendu (un SVG s'agrandit sans perte)

T = lambda key, label, ext: Target(key, label, ext, "Image")  # noqa: E731
TARGETS = [
    T("jpg", "JPEG", ".jpg"),
    T("png", "PNG", ".png"),
    T("webp", "WebP", ".webp"),
    T("heic", "HEIC", ".heic"),
    T("avif", "AVIF", ".avif"),
    T("tiff", "TIFF", ".tiff"),
    T("bmp", "BMP", ".bmp"),
    T("gif", "GIF", ".gif"),
    T("ico", "ICO (icône)", ".ico"),
]
PDF_TARGET = Target("pdf", "PDF", ".pdf", "Document")

_heif_ready = False


def _ensure_heif() -> bool:
    global _heif_ready
    if not _heif_ready:
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
            _heif_ready = True
        except ImportError:
            log.warning("pillow-heif absent : HEIC non pris en charge")
    return _heif_ready


def _has(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


def _avif_ok() -> bool:
    from PIL import features
    return bool(features.check("avif"))


# --------------------------------------------------------------------------- lecture

def _open_raw(src: Path):
    """Développe un fichier RAW. Repli sur l'aperçu JPEG intégré si LibRaw échoue
    (ex. certains ProRAW récents compressés en JPEG XL)."""
    from PIL import Image
    import rawpy

    exif = None
    try:  # les RAW sont souvent des TIFF : on tente de récupérer l'EXIF via Pillow
        with Image.open(src) as probe:
            exif = probe.getexif()
    except Exception:
        pass

    try:
        with rawpy.imread(str(src)) as raw:
            rgb = raw.postprocess(use_camera_wb=True, output_bps=8)
        img = Image.fromarray(rgb)
        return img, exif  # rawpy applique déjà la rotation
    except Exception as e:
        log.warning("Développement RAW impossible (%s), tentative avec l'aperçu intégré", e)

    try:
        with rawpy.imread(str(src)) as raw:
            thumb = raw.extract_thumb()
        if thumb.format == rawpy.ThumbFormat.JPEG:
            img = Image.open(io.BytesIO(thumb.data))
            img.load()
        else:
            img = Image.fromarray(thumb.data)
        from PIL import ImageOps
        return ImageOps.exif_transpose(img), exif
    except Exception as e:
        log.warning("Aperçu RAW indisponible (%s), dernier recours via Pillow", e)

    try:
        img = Image.open(src)
        img.load()
        return img, exif
    except Exception as e:
        raise ConversionError(f"Impossible de lire le fichier RAW {src.name} ({e}).") from e


def _open_svg(src: Path):
    from PIL import Image
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    try:
        with fitz.open(str(src)) as doc:
            page = doc[0]
            zoom = SVG_SIDE / max(page.rect.width, page.rect.height, 1)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=True)
            return Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
    except Exception as e:
        raise ConversionError(f"Impossible de lire le SVG {src.name} ({e}).") from e


def load_image(src: Path):
    """Retourne (image Pillow orientée correctement, exif Pillow ou None)."""
    from PIL import Image, ImageOps

    ext = src.suffix.lower()
    if ext in SVG_EXTS:
        return _open_svg(src), None
    if ext in RAW_EXTS:
        img, exif = _open_raw(src)
    else:
        if ext in HEIF_EXTS and not _ensure_heif():
            raise ConversionError("Le module HEIC (pillow-heif) n'est pas installé.")
        img = Image.open(src)
        exif = img.getexif()
        if getattr(img, "n_frames", 1) == 1:
            img = ImageOps.exif_transpose(img)  # applique la rotation iPhone
    if exif is not None:
        exif[0x0112] = 1  # orientation déjà appliquée aux pixels
    return img, exif


def _to_8bit(img):
    """Ramène les modes 16/32 bits ou flottants vers du 8 bits."""
    from PIL import Image
    if img.mode in ("I;16", "I;16B", "I;16L", "I", "F"):
        import numpy as np
        arr = np.asarray(img).astype("float64")
        lo, hi = float(arr.min()), float(arr.max())
        arr = (arr - lo) / (hi - lo or 1) * 255.0
        return Image.fromarray(arr.astype("uint8"), "L")
    if img.mode == "CMYK":
        return img.convert("RGB")
    return img


def _flatten(img, background=(255, 255, 255)):
    """Supprime la transparence (pour JPEG, BMP, PDF…) en posant l'image sur fond blanc."""
    from PIL import Image
    img = _to_8bit(img)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, background)
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
    return img.convert("RGB") if img.mode not in ("RGB", "L") else img


def _keep_alpha(img):
    img = _to_8bit(img)
    if img.mode in ("RGB", "RGBA", "L", "LA"):
        return img
    has_alpha = "A" in img.getbands() or "transparency" in img.info
    return img.convert("RGBA" if has_alpha else "RGB")


def save_image(img, exif, target_key: str, dest: Path, opts: ConvertOptions) -> None:
    from PIL import Image

    q = max(1, min(100, int(opts.quality)))
    extra = {}
    if opts.keep_metadata:
        if exif is not None and len(exif):
            try:
                extra["exif"] = exif.tobytes()
            except Exception:
                log.debug("EXIF non sérialisable, ignoré")
        icc = img.info.get("icc_profile")
        if icc:
            extra["icc_profile"] = icc

    animated = getattr(img, "n_frames", 1) > 1 and getattr(img, "is_animated", False)

    if target_key == "jpg":
        _flatten(img).save(dest, "JPEG", quality=q, optimize=True, progressive=True,
                           subsampling=0 if q >= 90 else 2, **extra)
    elif target_key == "png":
        _keep_alpha(img).save(dest, "PNG", optimize=False, compress_level=6, **extra)
    elif target_key == "webp":
        if animated:
            img.save(dest, "WEBP", save_all=True, quality=q)
        else:
            _keep_alpha(img).save(dest, "WEBP", quality=q, method=4, **extra)
    elif target_key == "heic":
        if not _ensure_heif():
            raise ConversionError("Le module HEIC (pillow-heif) n'est pas installé.")
        _keep_alpha(img).save(dest, "HEIF", quality=q, **extra)
    elif target_key == "avif":
        _keep_alpha(img).save(dest, "AVIF", quality=q, **extra)
    elif target_key == "tiff":
        _keep_alpha(img).save(dest, "TIFF", compression="tiff_adobe_deflate", **extra)
    elif target_key == "bmp":
        _flatten(img).save(dest, "BMP")
    elif target_key == "gif":
        if animated:
            img.save(dest, "GIF", save_all=True, optimize=True)
        else:
            _keep_alpha(img).save(dest, "GIF", optimize=True)
    elif target_key == "ico":
        im = _keep_alpha(img).convert("RGBA")
        side = max(im.size)
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        square.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
        square.save(dest, "ICO", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256) if s <= side] or [(side, side)])
    elif target_key == "pdf":
        _flatten(img).save(dest, "PDF", resolution=150.0)
    else:
        raise ConversionError(f"Format de sortie inconnu : {target_key}")


def _convert(src: Path, target: Target, out: Output, opts: ConvertOptions) -> list[Path]:
    img, exif = load_image(src)
    opts.check_cancel()
    dest = out.file(target.ext)
    try:
        save_image(img, exif, target.key, dest, opts)
    except Exception:
        if dest.exists():
            dest.unlink(missing_ok=True)  # pas de fichier à moitié écrit
        raise
    finally:
        img.close()
    return [dest]


def _svg_to_pdf(src: Path, target: Target, out: Output, opts: ConvertOptions) -> list[Path]:
    """SVG → PDF vectoriel (net à toutes les tailles)."""
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    dest = out.file(".pdf")
    try:
        with fitz.open(str(src)) as doc, fitz.open("pdf", doc.convert_to_pdf()) as pdf:
            pdf.save(str(dest), deflate=True)
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise ConversionError(f"Impossible de convertir le SVG {src.name} ({e}).") from e
    return [dest]


def register(reg: Registry) -> None:
    raw_ok = lambda: _has("rawpy")  # noqa: E731
    heif_ok = lambda: _has("pillow_heif")  # noqa: E731
    svg_ok = lambda: _has("pymupdf") or _has("fitz")  # noqa: E731
    for t in TARGETS:
        avail = {"heic": heif_ok, "avif": _avif_ok}.get(t.key)
        reg.add(SVG_EXTS, t, _convert, available=(lambda a=avail: svg_ok() and (a is None or a())))
        reg.add(STD_EXTS, t, _convert, available=avail)
        reg.add(HEIF_EXTS, t, _convert, available=(lambda a=avail: heif_ok() and (a is None or a())))
        reg.add(RAW_EXTS, t, _convert, available=(lambda a=avail: raw_ok() and (a is None or a())))
    # image → PDF (une page par image ; la fusion multi-fichiers est dans documents.py)
    reg.add(STD_EXTS, PDF_TARGET, _convert)
    reg.add(HEIF_EXTS, PDF_TARGET, _convert, available=heif_ok)
    reg.add(RAW_EXTS, PDF_TARGET, _convert, available=raw_ok)
    reg.add(SVG_EXTS, PDF_TARGET, _svg_to_pdf, available=svg_ok)
