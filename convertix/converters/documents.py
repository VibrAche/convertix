"""Conversions de documents.

Moteurs utilisés, du plus fidèle au plus simple :
  1. Microsoft Office (Word / Excel / PowerPoint) via COM — Windows uniquement, si installé ;
  2. LibreOffice en mode headless — Windows / Mac / Linux, si installé ;
  3. Bibliothèques Python embarquées : PyMuPDF (PDF), pdf2docx (PDF → Word),
     python-docx (Word → texte), openpyxl (CSV ↔ Excel).
"""
from __future__ import annotations

import csv
import functools
import io
import logging
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from ..engine import ConversionError, ConvertOptions, Output, Registry, Target
from ..proc import run

log = logging.getLogger(__name__)

WORD_EXTS = {".doc", ".docx", ".docm", ".dot", ".dotx", ".odt", ".rtf"}
TEXT_EXTS = {".txt"}
EXCEL_EXTS = {".xls", ".xlsx", ".xlsm", ".xlsb", ".ods"}
CSV_EXTS = {".csv"}
PPT_EXTS = {".ppt", ".pptx", ".pptm", ".pps", ".ppsx", ".odp"}
PDF_EXTS = {".pdf"}
EBOOK_EXTS = {".epub", ".mobi", ".fb2", ".xps", ".oxps", ".cbz"}  # lus directement par PyMuPDF

D = lambda key, label, ext, g="Document": Target(key, label, ext, g)  # noqa: E731
PDF = D("pdf", "PDF", ".pdf")
DOCX = D("docx", "Word (DOCX)", ".docx")
ODT = D("odt", "OpenDocument (ODT)", ".odt")
RTF = D("rtf", "RTF", ".rtf")
TXT = D("txt", "Texte brut (TXT)", ".txt")
XLSX = D("xlsx", "Excel (XLSX)", ".xlsx", "Tableur")
ODS = D("ods", "OpenDocument (ODS)", ".ods", "Tableur")
CSV = D("csv", "CSV", ".csv", "Tableur")
PPTX = D("pptx", "PowerPoint (PPTX)", ".pptx", "Présentation")
ODP = D("odp", "OpenDocument (ODP)", ".odp", "Présentation")
PNG_PAGES = D("png", "PNG", ".png", "Image")
JPG_PAGES = D("jpg", "JPEG", ".jpg", "Image")
SVG_PAGES = D("svg", "SVG", ".svg", "Image")

from .images import ALL_IMAGE_EXTS  # noqa: E402

MERGEABLE = PDF_EXTS | ALL_IMAGE_EXTS


# =========================================================================== détection des moteurs

@functools.lru_cache(maxsize=None)
def ms_office_app(progid: str) -> bool:
    """Vrai si l'application Office (ex. 'Word.Application') est enregistrée en COM."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        import win32com.client  # noqa: F401  (pywin32 doit être présent)
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid + r"\CLSID"))
        return True
    except Exception:
        return False


@functools.lru_cache(maxsize=None)
def soffice_path() -> str | None:
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    cands = []
    if sys.platform == "win32":
        for env in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
            base = os.environ.get(env)
            if base:
                cands.append(Path(base) / "LibreOffice" / "program" / "soffice.exe")
    elif sys.platform == "darwin":
        cands.append(Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"))
    for c in cands:
        if c.exists():
            return str(c)
    return None


def _has(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


word_ok = lambda: ms_office_app("Word.Application")  # noqa: E731
excel_ok = lambda: ms_office_app("Excel.Application")  # noqa: E731
ppt_ok = lambda: ms_office_app("PowerPoint.Application")  # noqa: E731
lo_ok = lambda: soffice_path() is not None  # noqa: E731
fitz_ok = lambda: _has("pymupdf") or _has("fitz")  # noqa: E731


def _fitz():
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    return fitz


# =========================================================================== Microsoft Office (COM)

class _Com:
    """Contexte COM pour un thread de travail."""

    def __enter__(self):
        import pythoncom
        pythoncom.CoInitialize()
        return self

    def __exit__(self, *exc):
        import pythoncom
        pythoncom.CoUninitialize()


WORD_FMT = {"pdf": 17, "docx": 16, "odt": 23, "rtf": 6, "txt": 2}
EXCEL_FMT = {"xlsx": 51, "ods": 60, "csv": 62}  # 62 = CSV UTF-8 (feuille active)
PPT_FMT = {"pdf": 32, "pptx": 24, "odp": 35}


def _word(src: Path, target: Target, out: Output, opts: ConvertOptions) -> list[Path]:
    import win32com.client
    dest = out.file(target.ext)
    with _Com():
        app = doc = None
        try:
            app = win32com.client.DispatchEx("Word.Application")
            app.Visible = False
            app.DisplayAlerts = 0
            # PasswordDocument factice : un document protégé échoue au lieu d'ouvrir une invite invisible
            doc = app.Documents.Open(str(src), ConfirmConversions=False, ReadOnly=True,
                                     AddToRecentFiles=False, Visible=False, PasswordDocument="convertix")
            if target.key == "txt":
                doc.SaveAs2(str(dest), FileFormat=2, Encoding=65001)
            else:
                doc.SaveAs2(str(dest), FileFormat=WORD_FMT[target.key])
        except Exception as e:
            dest.unlink(missing_ok=True)
            raise ConversionError(f"Word n'a pas pu convertir {src.name} (document protégé ou corrompu ?) : {e}") from e
        finally:
            if doc is not None:
                doc.Close(0)
                doc = None  # libérer le document avant Quit (voir _excel)
            if app is not None:
                app.Quit()
            app = None  # libérer les objets COM avant CoUninitialize
    return [dest]


def _excel(src: Path, target: Target, out: Output, opts: ConvertOptions) -> list[Path]:
    import win32com.client
    dest = out.file(target.ext)
    with _Com():
        app = wb = None
        try:
            app = win32com.client.DispatchEx("Excel.Application")
            app.Visible = False
            app.DisplayAlerts = False
            # Local=True : séparateur « ; » des CSV français ; Password factice : pas d'invite bloquante
            wb = app.Workbooks.Open(str(src), ReadOnly=True, AddToMru=False, Local=True, Password="convertix")
            if target.key == "pdf":
                wb.ExportAsFixedFormat(0, str(dest))
            else:
                wb.SaveAs(str(dest), FileFormat=EXCEL_FMT[target.key], Local=True)
        except Exception as e:
            dest.unlink(missing_ok=True)
            raise ConversionError(f"Excel n'a pas pu convertir {src.name} : {e}") from e
        finally:
            # libérer le classeur AVANT Quit : sinon le proxy pointe vers un Excel fermé (RPC_E_DISCONNECTED)
            if wb is not None:
                wb.Close(False)
                wb = None
            if app is not None:
                app.Quit()
            app = None
    return [dest]


def _powerpoint(src: Path, target: Target, out: Output, opts: ConvertOptions) -> list[Path]:
    import win32com.client
    dest = out.file(target.ext)
    with _Com():
        app = pres = None
        try:
            # PowerPoint n'a qu'une instance : si l'utilisateur l'a ouvert, on réutilise la sienne
            app = win32com.client.DispatchEx("PowerPoint.Application")
            pres = app.Presentations.Open(str(src), ReadOnly=True, Untitled=False, WithWindow=False)
            pres.SaveAs(str(dest), PPT_FMT[target.key])
        except Exception as e:
            dest.unlink(missing_ok=True)
            raise ConversionError(f"PowerPoint n'a pas pu convertir {src.name} : {e}") from e
        finally:
            if pres is not None:
                pres.Close()
                pres = None
            if app is not None and app.Presentations.Count == 0:
                app.Quit()  # ne jamais fermer un PowerPoint où l'utilisateur travaille
            pres = app = None
    return [dest]


# =========================================================================== LibreOffice

LO_FILTER = {
    "pdf": "pdf",
    "docx": "docx:MS Word 2007 XML",
    "odt": "odt",
    "rtf": "rtf",
    "txt": "txt:Text (encoded):UTF8",
    "xlsx": "xlsx:Calc MS Excel 2007 XML",
    "ods": "ods",
    "csv": "csv:Text - txt - csv (StarCalc):44,34,76,1",
    "pptx": "pptx:Impress MS PowerPoint 2007 XML",
    "odp": "odp",
}


def _libreoffice(src: Path, target: Target, out: Output, opts: ConvertOptions) -> list[Path]:
    exe = soffice_path()
    if not exe:
        raise ConversionError("LibreOffice est introuvable.")
    with tempfile.TemporaryDirectory(prefix="convertix-lo-") as tmp:
        tmp = Path(tmp)
        profile = (tmp / "profile").as_uri()  # profil isolé : marche même si LibreOffice est ouvert
        run([exe, f"-env:UserInstallation={profile}", "--headless", "--norestore",
             "--convert-to", LO_FILTER[target.key], "--outdir", str(tmp / "out"), str(src)],
            opts, timeout=600, what="LibreOffice")
        produced = list((tmp / "out").glob("*"))
        if not produced:
            raise ConversionError("LibreOffice n'a produit aucun fichier.")
        dest = out.file(target.ext)
        shutil.move(str(produced[0]), dest)
    return [dest]


# =========================================================================== Python pur

def _pdf_to_docx(src: Path, target: Target, out: Output, opts: ConvertOptions) -> list[Path]:
    from pdf2docx import Converter
    dest = out.file(".docx")
    cv = Converter(str(src))
    try:
        cv.convert(str(dest))
    finally:
        cv.close()
    return [dest]


def _pdf_to_images(src: Path, target: Target, out: Output, opts: ConvertOptions, dpi: int = 200) -> list[Path]:
    fitz = _fitz()
    results: list[Path] = []
    with fitz.open(str(src)) as doc:
        if doc.needs_pass:
            raise ConversionError(f"{src.name} est protégé par mot de passe.")
        n = doc.page_count
        folder = out.folder(" - pages") if n > 1 else None
        for i, page in enumerate(doc):
            opts.check_cancel()
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            if folder:
                dest = folder / f"{src.stem} - page {i + 1:0{len(str(n))}d}{target.ext}"
            else:
                dest = out.file(target.ext)
            if target.key == "jpg":
                pix.save(str(dest), jpg_quality=opts.quality)
            else:
                pix.save(str(dest))
            results.append(dest)
    return [results[0].parent] if len(results) > 1 else results


def _pdf_to_svg(src: Path, target: Target, out: Output, opts: ConvertOptions) -> list[Path]:
    """PDF → un SVG vectoriel par page (textes et tracés restent nets)."""
    fitz = _fitz()
    results: list[Path] = []
    with fitz.open(str(src)) as doc:
        if doc.needs_pass:
            raise ConversionError(f"{src.name} est protégé par mot de passe.")
        n = doc.page_count
        folder = out.folder(" - pages") if n > 1 else None
        for i, page in enumerate(doc):
            opts.check_cancel()
            dest = folder / f"{src.stem} - page {i + 1:0{len(str(n))}d}.svg" if folder else out.file(".svg")
            dest.write_text(page.get_svg_image(text_as_path=False), encoding="utf-8")
            results.append(dest)
    return [results[0].parent] if len(results) > 1 else results


def _ebook_to_pdf(src: Path, target: Target, out: Output, opts: ConvertOptions) -> list[Path]:
    """EPUB, MOBI, FB2, XPS, CBZ → PDF (mise en page A5 de PyMuPDF pour les livres)."""
    fitz = _fitz()
    dest = out.file(".pdf")
    try:
        with fitz.open(str(src)) as doc, fitz.open("pdf", doc.convert_to_pdf()) as pdf:
            pdf.save(str(dest), garbage=3, deflate=True)
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise ConversionError(f"Impossible de lire {src.name} ({e}).") from e
    return [dest]


def _pdf_to_txt(src: Path, target: Target, out: Output, opts: ConvertOptions) -> list[Path]:
    fitz = _fitz()
    dest = out.file(".txt")
    with fitz.open(str(src)) as doc:
        text = "\n\f\n".join(page.get_text() for page in doc)
    dest.write_text(text, encoding="utf-8")
    return [dest]


def _office_to_images(src: Path, target: Target, out: Output, opts: ConvertOptions) -> list[Path]:
    """Présentation → une image par diapositive (passe par un PDF temporaire)."""
    from ..engine import Output as _Out, registry
    with tempfile.TemporaryDirectory(prefix="convertix-") as tmp:
        tmp_opts = ConvertOptions(quality=opts.quality, output_dir=Path(tmp), cancel=opts.cancel)
        rule = registry().rule_for(src.suffix.lower(), "pdf")
        if rule is None:
            raise ConversionError("Aucun moteur (Office ou LibreOffice) pour lire cette présentation.")
        pdf = rule.func(src, PDF, _Out(src, tmp_opts), tmp_opts)[0]
        # on renomme le PDF temporaire pour que les images portent le nom d'origine
        return _pdf_to_images(pdf, target, out, opts, dpi=150)


def _docx_to_txt(src: Path, target: Target, out: Output, opts: ConvertOptions) -> list[Path]:
    import docx
    d = docx.Document(str(src))
    lines = [p.text for p in d.paragraphs]
    for table in d.tables:
        for row in table.rows:
            lines.append("\t".join(c.text for c in row.cells))
    dest = out.file(".txt")
    dest.write_text("\n".join(lines), encoding="utf-8")
    return [dest]


_NUM = re.compile(r"^-?\d{1,15}([.,]\d+)?$")


def _read_csv(src: Path) -> list[list[str]]:
    raw = src.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialect = csv.Sniffer().sniff(text[:20000], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return list(csv.reader(io.StringIO(text), dialect))


def _csv_to_xlsx(src: Path, target: Target, out: Output, opts: ConvertOptions) -> list[Path]:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = src.stem[:31] or "Feuille1"
    for row in _read_csv(src):
        conv = []
        for v in row:
            if _NUM.match(v.strip()):
                s = v.strip().replace(",", ".")
                conv.append(float(s) if "." in s else int(s))
            else:
                conv.append(v)
        ws.append(conv)
    dest = out.file(".xlsx")
    wb.save(dest)
    return [dest]


def _xlsx_to_csv(src: Path, target: Target, out: Output, opts: ConvertOptions) -> list[Path]:
    """Une feuille → un CSV ; plusieurs feuilles → un CSV par feuille. Séparateur « ; » (Excel FR)."""
    from openpyxl import load_workbook
    wb = load_workbook(str(src), read_only=True, data_only=True)
    sheets = wb.worksheets
    results = []
    for ws in sheets:
        stem = src.stem if len(sheets) == 1 else f"{src.stem} - {ws.title}"
        dest = out.file(".csv", stem=re.sub(r'[\\/:*?"<>|]', "_", stem))
        with open(dest, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            for row in ws.iter_rows(values_only=True):
                w.writerow(["" if v is None else v for v in row])
        results.append(dest)
    wb.close()
    return results


# =========================================================================== fusion PDF

def merge_to_pdf(paths: list[Path], opts: ConvertOptions) -> Path:
    """Assemble images (y compris HEIC / RAW) et PDF dans un seul PDF, dans l'ordre donné.
    Les images sont centrées sur une page A4 dans le sens de l'image."""
    from .images import _flatten, load_image
    fitz = _fitz()
    if not paths:
        raise ConversionError("Aucun fichier à fusionner.")
    out = Output(paths[0], opts)
    dest = out.file(".pdf", stem=f"{paths[0].stem} - fusion")
    A4 = (595.0, 842.0)
    margin = 18.0
    with fitz.open() as doc:
        for p in paths:
            opts.check_cancel()
            ext = p.suffix.lower()
            if ext in PDF_EXTS:
                with fitz.open(str(p)) as src:
                    doc.insert_pdf(src)
                continue
            img, _ = load_image(p)
            img = _flatten(img)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=opts.quality)
            w, h = img.size
            pw, ph = A4 if h >= w else (A4[1], A4[0])
            scale = min((pw - 2 * margin) / w, (ph - 2 * margin) / h)
            iw, ih = w * scale, h * scale
            page = doc.new_page(width=pw, height=ph)
            rect = fitz.Rect((pw - iw) / 2, (ph - ih) / 2, (pw + iw) / 2, (ph + ih) / 2)
            page.insert_image(rect, stream=buf.getvalue())
            img.close()
        doc.save(str(dest), garbage=3, deflate=True)
    return dest


# =========================================================================== enregistrement

def register(reg: Registry) -> None:
    # --- PDF → …
    reg.add(PDF_EXTS, DOCX, _pdf_to_docx, available=lambda: _has("pdf2docx"))
    reg.add(PDF_EXTS, PNG_PAGES, _pdf_to_images, available=fitz_ok)
    reg.add(PDF_EXTS, JPG_PAGES, _pdf_to_images, available=fitz_ok)
    reg.add(PDF_EXTS, TXT, _pdf_to_txt, available=fitz_ok)
    reg.add(PDF_EXTS, SVG_PAGES, _pdf_to_svg, available=fitz_ok)

    # --- Livres numériques et documents XPS (PyMuPDF les ouvre comme des PDF)
    reg.add(EBOOK_EXTS, PDF, _ebook_to_pdf, available=fitz_ok)
    reg.add(EBOOK_EXTS, TXT, _pdf_to_txt, available=fitz_ok)
    reg.add(EBOOK_EXTS, PNG_PAGES, _pdf_to_images, available=fitz_ok)
    reg.add(EBOOK_EXTS, JPG_PAGES, _pdf_to_images, available=fitz_ok)

    # --- Word / texte
    for t in (PDF, DOCX, ODT, RTF, TXT):
        reg.add(WORD_EXTS, t, _word, available=word_ok, priority=10)
        reg.add(WORD_EXTS, t, _libreoffice, available=lo_ok, priority=5)
    reg.add({".docx", ".docm", ".dotx"}, TXT, _docx_to_txt, available=lambda: _has("docx"), priority=1)
    for t in (PDF, DOCX):
        reg.add(TEXT_EXTS, t, _word, available=word_ok, priority=10)
        reg.add(TEXT_EXTS, t, _libreoffice, available=lo_ok, priority=5)

    # --- Tableurs
    for t in (PDF, XLSX, ODS, CSV):
        reg.add(EXCEL_EXTS, t, _excel, available=excel_ok, priority=10)
        reg.add(EXCEL_EXTS, t, _libreoffice, available=lo_ok, priority=5)
    reg.add({".xlsx", ".xlsm"}, CSV, _xlsx_to_csv, available=lambda: _has("openpyxl"), priority=20)
    reg.add(CSV_EXTS, XLSX, _csv_to_xlsx, available=lambda: _has("openpyxl"), priority=20)
    for t in (PDF, ODS):
        reg.add(CSV_EXTS, t, _excel, available=excel_ok, priority=10)
        reg.add(CSV_EXTS, t, _libreoffice, available=lo_ok, priority=5)

    # --- Présentations
    for t in (PDF, PPTX, ODP):
        reg.add(PPT_EXTS, t, _powerpoint, available=ppt_ok, priority=10)
        reg.add(PPT_EXTS, t, _libreoffice, available=lo_ok, priority=5)
    for t in (PNG_PAGES, JPG_PAGES):
        reg.add(PPT_EXTS, t, _office_to_images, available=lambda: (ppt_ok() or lo_ok()) and fitz_ok())
