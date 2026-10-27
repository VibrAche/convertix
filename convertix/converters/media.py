"""Conversions audio / vidéo via ffmpeg (binaire fourni par imageio-ffmpeg, embarqué dans l'app)."""
from __future__ import annotations

import functools
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..engine import ConversionError, ConvertOptions, Output, Registry, Target
from ..proc import NO_WINDOW, run

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


# HDR (vidéos iPhone en HLG / Dolby Vision) → SDR : sinon les couleurs sortent délavées en H.264
TONEMAP = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
           "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p")
# codecs audio qu'un MP4 / MOV accepte tels quels (copie sans réencodage)
COPY_AUDIO = {"aac", "mp3", "alac", "ac3", "eac3"}


@dataclass
class MediaInfo:
    duration: float = 0.0          # secondes
    vcodec: str = ""               # ex. "h264", "hevc" ; vide si pas de vidéo
    acodecs: list[str] = field(default_factory=list)
    hdr: bool = False


def probe(src: Path) -> MediaInfo:
    """Lit durée, codecs et HDR depuis la sortie de `ffmpeg -i` (pas besoin de ffprobe)."""
    info = MediaInfo()
    exe = ffmpeg_path()
    if not exe:
        return info
    try:
        res = subprocess.run([exe, "-hide_banner", "-nostdin", "-i", str(src)], capture_output=True,
                             stdin=subprocess.DEVNULL, timeout=30, creationflags=NO_WINDOW)
    except Exception:
        return info
    text = res.stderr.decode("utf-8", errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if m:
        info.duration = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    for line in text.splitlines():
        if (v := re.search(r"Stream #.*?Video: (\w+)", line)) and not info.vcodec and "attached pic" not in line:
            info.vcodec = v[1]
            info.hdr = bool(re.search(r"arib-std-b67|smpte2084", line))
        elif a := re.search(r"Stream #.*?Audio: (\w+)", line):
            info.acodecs.append(a[1])
    return info


@functools.lru_cache(maxsize=None)
def has_filter(name: str) -> bool:
    exe = ffmpeg_path()
    try:
        res = subprocess.run([exe, "-hide_banner", "-filters"], capture_output=True, timeout=15,
                             stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
        return re.search(rf"\s{re.escape(name)}\s", res.stdout.decode("utf-8", "replace")) is not None
    except Exception:
        return False


def _fast_copy(key: str, info: MediaInfo) -> bool:
    """MOV iPhone en H.264 → MP4 (ou l'inverse) : on change juste l'emballage, en une seconde, sans perte."""
    return key in ("mp4", "mov", "mkv") and info.vcodec == "h264" and not info.hdr \
        and set(info.acodecs) <= COPY_AUDIO


def _with_tonemap(args: list[str]) -> list[str]:
    """Ajoute le tonemapping HDR → SDR devant le filtre vidéo existant (ou en crée un)."""
    if "-vf" in args:
        i = args.index("-vf") + 1
        return args[:i] + [f"{TONEMAP},{args[i]}"] + args[i + 1:]
    return ["-vf", TONEMAP] + args


def _ffmpeg(src: Path, target: Target, out: Output, opts: ConvertOptions) -> list[Path]:
    exe = ffmpeg_path()
    if not exe:
        raise ConversionError("ffmpeg est introuvable.")
    info = probe(src)
    dest = out.file(target.ext)
    if target.group == "Audio":
        args = ["-vn", "-map_metadata", "0"] + _audio_args(target.key, opts.quality)
    elif _fast_copy(target.key, info):
        log.info("Copie rapide sans réencodage (%s)", info.vcodec)
        args = ["-map", "0:v:0", "-map", "0:a?", "-c", "copy", "-map_metadata", "0"]
        if target.key in ("mp4", "mov"):
            args += ["-movflags", "+faststart"]
    else:
        args = ["-map_metadata", "0"] + _video_args(target.key, opts.quality)
        if info.hdr and has_filter("zscale") and has_filter("tonemap"):
            log.info("Vidéo HDR : conversion des couleurs en SDR")
            args = _with_tonemap(args)

    def on_line(line: str) -> None:  # « out_time_us=12345678 » envoyé par -progress
        if info.duration > 0 and line.startswith("out_time_us="):
            us = line.split("=", 1)[1]
            if us.isdigit():
                opts.report(int(us) / 1e6 / info.duration)

    cmd = [exe, "-hide_banner", "-nostdin", "-y", "-i", str(src)] + args + \
          ["-progress", "pipe:1", "-nostats", str(dest)]
    try:
        run(cmd, opts, what="ffmpeg", on_line=on_line)
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
