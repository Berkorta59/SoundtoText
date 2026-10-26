from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


SUPPORTED_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma",
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v",
}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    duration: float
    size_bytes: int
    has_video: bool


def validate_media_path(path: str | Path) -> Path:
    media_path = Path(path).expanduser()
    if not media_path.is_file():
        raise FileNotFoundError(f"Dosya bulunamadı: {media_path}")
    if media_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Desteklenmeyen dosya biçimi: {media_path.suffix or '(uzantısız)'}")
    return media_path.resolve()


def probe_media(path: str | Path) -> MediaInfo:
    media_path = validate_media_path(path)
    try:
        import av
    except ImportError as error:
        raise RuntimeError("Medya bilgisi için PyAV kurulu değil. requirements.txt dosyasındaki paketleri yükleyin.") from error
    try:
        with av.open(str(media_path)) as container:
            audio_streams = list(container.streams.audio)
            if not audio_streams:
                raise ValueError("Dosyada kullanılabilir bir ses kanalı bulunamadı.")
            duration = float(container.duration / av.time_base) if container.duration else 0.0
            if not duration:
                durations = [
                    float(stream.duration * stream.time_base)
                    for stream in audio_streams
                    if stream.duration is not None and stream.time_base is not None
                ]
                duration = max(durations, default=0.0)
            if duration <= 0:
                raise ValueError("Medya süresi okunamadı; dosya bozuk veya biçim desteklenmiyor olabilir.")
            return MediaInfo(
                path=media_path,
                duration=duration,
                size_bytes=media_path.stat().st_size,
                has_video=media_path.suffix.lower() in VIDEO_EXTENSIONS or bool(container.streams.video),
            )
    except (ValueError, RuntimeError):
        raise
    except Exception as error:
        raise ValueError(f"Medya dosyası açılamadı: {error}") from error


def format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{secs:02}" if hours else f"{minutes:02}:{secs:02}"


def format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
