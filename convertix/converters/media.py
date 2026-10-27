"""Conversions audio / vidéo via ffmpeg (binaire fourni par imageio-ffmpeg, embarqué dans l'app)."""
from __future__ import annotations

import functools
import logging
import shutil
from pathlib import Path

from ..engine import ConversionError, ConvertOptions, Output, Registry, Target
from ..proc import run

log = logging.getLogger(__name__)

VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".avi", ".mkv", ".webm", ".wmv", ".flv", ".3gp",
              ".mts", ".m2ts", ".mpg", ".mpeg", ".ts", ".ogv"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wma",
              ".aiff", ".aif", ".caf", ".amr", ".alac"}

V = lambda k, l, e: Target(k, l, e, "Vidéo")  # noqa: E731
A = lambda k, l, e: Target(k, l, e, "Audio")  # noqa: E731
VIDEO_TARGETS = [
    V("mp4", "MP4 (H.264)", ".mp4"),
    V("mov", "MOV", ".mov"),
    V("mkv", "MKV", ".mkv"),
    V("webm", "WebM", ".webm"),
    V("gif", "GIF animé", ".gif"),
]
AUDIO_TARGETS = [
    A("mp3", "MP3", ".mp3"),
    A("m4a", "M4A (AAC)", ".m4a"),
    A("wav", "WAV", ".wav"),
    A("flac", "FLAC", ".flac"),
    A("ogg", "OGG (Vorbis)", ".ogg"),
    A("opus", "Opus", ".opus"),
]


@functools.lru_cache(maxsize=None)
def ffmpeg_path() -> str | None:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def ffmpeg_ok() -> bool:
    return ffmpeg_path() is not None


def _crf(q: int) -> int:
    """Qualité 1-100 → CRF x264 (≈ 18 à 100 %, ≈ 28 à 50 %)."""
    return int(round(18 + (100 - max(1, min(100, q))) * 0.2))


def _audio_args(key: str, q: int) -> list[str]:
    br = "256k" if q >= 90 else "192k" if q >= 70 else "128k"
    return {
        "mp3": ["-c:a", "libmp3lame", "-b:a", br],
        "m4a": ["-c:a", "aac", "-b:a", br],
        "wav": ["-c:a", "pcm_s16le"],
        "flac": ["-c:a", "flac"],
        "ogg": ["-c:a", "libvorbis", "-q:a", "6" if q >= 80 else "4"],
        "opus": ["-c:a", "libopus", "-b:a", "160k" if q >= 80 else "96k"],
    }[key]


def _video_args(key: str, q: int) -> list[str]:
    crf = str(_crf(q))
    h264 = ["-c:v", "libx264", "-preset", "medium", "-crf", crf, "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k"]
    return {
        "mp4": h264 + ["-movflags", "+faststart"],
        "mov": h264 + ["-movflags", "+faststart"],
        "mkv": h264,
        "webm": ["-c:v", "libvpx-vp9", "-crf", str(min(63, int(crf) + 12)), "-b:v", "0",
                 "-deadline", "good", "-cpu-used", "4", "-row-mt", "1",
                 "-c:a", "libopus", "-b:a", "128k"],
        "gif": ["-vf", "fps=12,scale='min(720,iw)':-2:flags=lanczos,split[a][b];"
                       "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4",
                "-loop", "0", "-an"],
    }[key]


def _ffmpeg(src: Path, target: Target, out: Output, opts: ConvertOptions) -> list[Path]:
    exe = ffmpeg_path()
    if not exe:
        raise ConversionError("ffmpeg est introuvable.")
    dest = out.file(target.ext)
    if target.group == "Audio":
        args = ["-vn", "-map_metadata", "0"] + _audio_args(target.key, opts.quality)
    else:
        args = ["-map_metadata", "0"] + _video_args(target.key, opts.quality)
    cmd = [exe, "-hide_banner", "-nostdin", "-y", "-i", str(src)] + args + [str(dest)]
    try:
        run(cmd, opts, what="ffmpeg")
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return [dest]


def register(reg: Registry) -> None:
    for t in VIDEO_TARGETS:
        reg.add(VIDEO_EXTS, t, _ffmpeg, available=ffmpeg_ok)
    for t in AUDIO_TARGETS:
        # vidéo → audio = extraction de la bande son
        reg.add(VIDEO_EXTS | AUDIO_EXTS, t, _ffmpeg, available=ffmpeg_ok)
