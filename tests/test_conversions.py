"""Tests du moteur : chaque fichier d'exemple est converti vers chaque format proposé.

    pytest -q                 (tests rapides)
    pytest -q -m "not slow"   (sans vidéo / LibreOffice)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from convertix import engine  # noqa: E402
from convertix.engine import ConvertOptions  # noqa: E402
from tests.make_samples import make  # noqa: E402

RAW_DIR = Path(__file__).parent / "samples_raw"


@pytest.fixture(scope="session")
def samples(tmp_path_factory) -> list[Path]:
    files = make(tmp_path_factory.mktemp("samples"))
    if RAW_DIR.exists():
        supported = engine.registry().supported_inputs()
        files += sorted(p for p in RAW_DIR.iterdir() if p.is_file() and p.suffix.lower() in supported)
    return files


def test_every_sample_has_targets(samples):
    for f in samples:
        assert engine.targets_for([f]), f"aucun format proposé pour {f.name}"


def test_convert_all(samples, tmp_path):
    failures = []
    count = 0
    for f in samples:
        for target, _ in engine.targets_for([f]):
            out_dir = tmp_path / f"{f.stem}_{f.suffix[1:]}_{target.key}"
            try:
                results = engine.convert(f, target.key, ConvertOptions(output_dir=out_dir))
                assert results, "aucun résultat"
                for r in results:
                    assert r.exists(), f"{r} absent"
                    if r.is_file():
                        assert r.stat().st_size > 0, f"{r} vide"
                count += 1
            except Exception as e:  # on collecte tout pour un rapport complet
                failures.append(f"{f.name} → {target.key}: {e}")
    print(f"\n{count} conversions réussies")
    assert not failures, "\n".join(failures)


def test_exif_orientation_applied(samples, tmp_path):
    from PIL import Image
    src = next(p for p in samples if p.name == "orientation.jpg")
    (png,) = engine.convert(src, "png", ConvertOptions(output_dir=tmp_path))
    with Image.open(png) as im:
        assert im.size == (300, 400)  # 400x300 tourné de 90°


def test_no_overwrite(samples, tmp_path):
    src = next(p for p in samples if p.name == "transparent.png")
    a = engine.convert(src, "jpg", ConvertOptions(output_dir=tmp_path))[0]
    b = engine.convert(src, "jpg", ConvertOptions(output_dir=tmp_path))[0]
    assert a != b and b.name == "transparent (1).jpg"


def test_merge_pdf(samples, tmp_path):
    files = engine.mergeable(samples)
    pdf = engine.merge_to_pdf(files, ConvertOptions(output_dir=tmp_path))
    import pymupdf
    with pymupdf.open(str(pdf)) as d:
        assert d.page_count >= len(files)


def test_csv_french_numbers(samples, tmp_path):
    from openpyxl import load_workbook
    src = next(p for p in samples if p.suffix == ".csv")
    (x,) = engine.convert(src, "xlsx", ConvertOptions(output_dir=tmp_path))
    ws = load_workbook(x).active
    assert ws["A2"].value == "Élodie" and ws["B2"].value == 12.5


def test_cancel(samples, tmp_path):
    src = next(p for p in samples if p.suffix == ".pdf")
    opts = ConvertOptions(output_dir=tmp_path)
    opts.cancel.set()
    with pytest.raises(engine.Cancelled):
        engine.convert(src, "png", opts)
