# -*- mode: python ; coding: utf-8 -*-
# Construction : pyinstaller packaging/convertix.spec --noconfirm   (depuis la racine du projet)
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT))
from convertix import APP_NAME, __version__  # noqa: E402

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

datas = [(str(ROOT / "assets"), "assets")]
datas += collect_data_files("imageio_ffmpeg")      # binaire ffmpeg
datas += collect_data_files("pillow_heif")
binaries = collect_dynamic_libs("rawpy") + collect_dynamic_libs("pillow_heif")

hidden = collect_submodules("convertix") + ["pillow_heif", "rawpy", "pdf2docx", "docx", "openpyxl", "pymupdf"]
if IS_WIN:
    hidden += ["win32com.client", "win32clipboard", "win32con", "pythoncom", "pywintypes"]
    hidden += collect_submodules("windows_toasts") + collect_submodules("winrt")
if IS_MAC:
    hidden += ["pynput.keyboard._darwin", "pynput.mouse._darwin"]

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "scipy", "pandas", "torch", "onnxruntime",
              "PySide6.QtWebEngineCore",
              "PySide6.Qt3DCore", "PySide6.QtQml", "PySide6.QtQuick"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    console=False,                      # pas de fenêtre noire
    icon=str(ROOT / "assets" / ("icon.icns" if IS_MAC else "icon.ico")),
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME, upx=False)

if IS_MAC:
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=str(ROOT / "assets" / "icon.icns"),
        bundle_identifier="com.convertix.app",
        info_plist={
            "CFBundleShortVersionString": __version__,
            "LSUIElement": True,  # app de barre de menus : pas d'icône dans le Dock
            "NSAppleEventsUsageDescription": "Convertix lit la sélection du Finder pour convertir vos fichiers.",
            "NSHighResolutionCapable": True,
        },
    )
