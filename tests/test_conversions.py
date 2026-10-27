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


def test_video_fast_copy_and_progress(samples, tmp_path):
    """MOV H.264 → MP4 : copie sans réencodage, et l'avancement remonte jusqu'à 100 %."""
    from convertix.converters import media
    src = next(p for p in samples if p.suffix == ".mov")
    info = media.probe(src)
    assert info.vcodec == "h264" and info.duration > 1 and media._fast_copy("mp4", info)
    seen: list[float] = []
    (mp4,) = engine.convert(src, "mp4", ConvertOptions(output_dir=tmp_path, progress=seen.append))
    assert media.probe(mp4).vcodec == "h264"
    assert seen and max(seen) > 0.9


def test_video_hdr_tonemap(tmp_path):
    """Vidéo HDR (HLG, comme l'iPhone) → MP4 : couleurs ramenées en SDR, H.264 8 bits."""
    import subprocess
    from convertix.converters import media
    if not (media.has_filter("zscale") and media.has_filter("tonemap")):
        pytest.skip("ffmpeg sans zscale/tonemap")
    src = tmp_path / "hdr.mov"
    make = subprocess.run([media.ffmpeg_path(), "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=duration=1:size=320x240:rate=10", "-c:v", "libx265", "-pix_fmt", "yuv420p10le",
                    "-x265-params", "colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc:log-level=error",
                    "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc",
                    "-tag:v", "hvc1", str(src)], capture_output=True)
    if make.returncode != 0:
        pytest.skip("ffmpeg sans encodeur x265 pour fabriquer la vidéo HDR de test")
    assert media.probe(src).hdr
    (mp4,) = engine.convert(src, "mp4", ConvertOptions(output_dir=tmp_path / "out"))
    out = media.probe(mp4)
    assert out.vcodec == "h264" and not out.hdr


def test_update_version_compare():
    from convertix.updates import is_newer
    assert is_newer("0.10.0", "0.9.3") and is_newer("v1.0.0", "0.2.0")
    assert not is_newer("0.2.0", "0.2.0") and not is_newer("0.1.9", "0.2.0")


def test_cancel(samples, tmp_path):
    src = next(p for p in samples if p.suffix == ".pdf")
    opts = ConvertOptions(output_dir=tmp_path)
    opts.cancel.set()
    with pytest.raises(engine.Cancelled):
        engine.convert(src, "png", opts)
