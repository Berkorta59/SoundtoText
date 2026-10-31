from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable

from app.core.formats import TranscriptSegment
from app.core.media import MediaInfo, compatible_media_path

ProgressCallback = Callable[[float, str], None]


class TranscriptionCancelled(Exception):
    pass


def model_cache_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "SoundtoText" / "models"


def available_cuda_devices() -> int:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count()
    except (ImportError, OSError, RuntimeError):
        return 0


def _is_cuda_runtime_error(error: RuntimeError) -> bool:
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "cublas", "cudnn", "cuda driver", "cuda error",
            "no cuda-capable device", "cuda runtime",
        )
    )


def _describe_cuda_error(error: RuntimeError) -> RuntimeError:
    return RuntimeError(
        f"CUDA başlatılamadı: {error}. CUDA 12 uyumlu çalışma kitaplıklarını kurun "
        "veya Ayarlar'da İşlem aygıtı seçimini Otomatik ya da İşlemci (CPU) yapın."
    )


class LocalTranscriber:
    def __init__(self) -> None:
        self._model = None
        self._model_key: tuple[str, str, str] | None = None

    def _load_model(self, name: str, device_choice: str, compute_type: str, progress: ProgressCallback):
        device = device_choice
        if device == "auto":
            device = "cuda" if available_cuda_devices() else "cpu"
        if device == "cuda" and not available_cuda_devices():
            raise RuntimeError("CUDA destekli bir aygıt bulunamadı. Ayarlardan CPU veya Otomatik seçin.")
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"
        key = (name, device, compute_type)
        if self._model is not None and self._model_key == key:
            return self._model

        progress(0, f"{name} modeli yükleniyor; ilk kullanımda indirilebilir…")
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise RuntimeError("faster-whisper kurulu değil. Kurulum betiğini çalıştırın.") from error
        try:
            self._model = WhisperModel(
                name,
                device=device,
                compute_type=compute_type,
                download_root=str(model_cache_path()),
            )
        except RuntimeError as error:
            if device_choice == "auto" and device == "cuda" and _is_cuda_runtime_error(error):
                progress(0, "CUDA kitaplıkları yüklenemedi; CPU ile devam ediliyor…")
                return self._load_model(name, "cpu", "int8", progress)
            if device == "cuda" and _is_cuda_runtime_error(error):
                raise _describe_cuda_error(error) from error
            raise
        self._model_key = key
        return self._model

    @staticmethod
    def _extract_audio(media: MediaInfo, cancel: threading.Event) -> Path:
        try:
            import imageio_ffmpeg
        except ImportError as error:
            raise RuntimeError("FFmpeg bulunamadı. imageio-ffmpeg paketini kurun.") from error

        temporary_audio = tempfile.NamedTemporaryFile(
            prefix="soundtotext-", suffix=".wav", delete=False
        )
        audio_path = Path(temporary_audio.name)
        temporary_audio.close()
        try:
            with compatible_media_path(media.path) as compatible_path:
                command = [
                    imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-y", "-v", "error",
                    "-i", str(compatible_path), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
                    "-c:a", "pcm_s16le", str(audio_path),
                ]
                with tempfile.TemporaryFile() as error_output:
                    try:
                        process = subprocess.Popen(
                            command, stdout=subprocess.DEVNULL, stderr=error_output
                        )
                    except OSError as error:
                        audio_path.unlink(missing_ok=True)
                        raise RuntimeError(f"FFmpeg başlatılamadı: {error}") from error
                    while process.poll() is None:
                        if cancel.wait(0.1):
                            process.terminate()
                            try:
                                process.wait(timeout=3)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait()
                            audio_path.unlink(missing_ok=True)
                            raise TranscriptionCancelled()
                    error_output.seek(0)
                    stderr = error_output.read().decode("utf-8", errors="replace")
        except OSError:
            audio_path.unlink(missing_ok=True)
            raise
        if process.returncode != 0:
            audio_path.unlink(missing_ok=True)
            if "matches no streams" in stderr.lower() or "does not contain any stream" in stderr.lower():
                raise ValueError("Dosyada kullanılabilir bir ses kanalı bulunamadı.")
            raise RuntimeError(f"Ses FFmpeg ile hazırlanamadı: {stderr.strip()[-1000:]}")
        return audio_path

    def transcribe(
        self,
        media: MediaInfo,
        *,
        model_name: str,
        language: str | None,
        task: str,
        device: str,
        compute_type: str,
        word_timestamps: bool,
        cancel: threading.Event,
        progress: ProgressCallback,
    ) -> tuple[list[TranscriptSegment], str | None]:
        audio_path: Path | None = None
        try:
            if cancel.is_set():
                raise TranscriptionCancelled()
            model = self._load_model(model_name, device, compute_type, progress)
            if cancel.is_set():
                raise TranscriptionCancelled()
            progress(0, "Ses hazırlanıyor…")
            audio_path = self._extract_audio(media, cancel)
            if cancel.is_set():
                raise TranscriptionCancelled()

            def transcribe_all(active_model):
                segments_iter, info = active_model.transcribe(
                    str(audio_path),
                    language=language,
                    task=task,
                    word_timestamps=word_timestamps,
                    vad_filter=True,
                )
                collected_segments: list[TranscriptSegment] = []
                for item in segments_iter:
                    if cancel.is_set():
                        raise TranscriptionCancelled()
                    collected_segments.append(
                        TranscriptSegment(float(item.start), float(item.end), item.text.strip())
                    )
                    progress(
                        min(99, int(item.end / media.duration * 100)),
                        "Transkripsiyon yapılıyor…",
                    )
                return collected_segments, getattr(info, "language", language)

            progress(0, "Transkripsiyon yapılıyor…")
            try:
                collected, detected_language = transcribe_all(model)
            except RuntimeError as error:
                if not (
                    device == "auto"
                    and self._model_key is not None
                    and self._model_key[1] == "cuda"
                    and _is_cuda_runtime_error(error)
                ):
                    if self._model_key is not None and self._model_key[1] == "cuda" and _is_cuda_runtime_error(error):
                        raise _describe_cuda_error(error) from error
                    raise
                progress(0, "CUDA çalışma kitaplığı eksik; CPU ile yeniden deneniyor…")
                self._model = None
                self._model_key = None
                model = self._load_model(model_name, "cpu", "int8", progress)
                if cancel.is_set():
                    raise TranscriptionCancelled()
                progress(0, "CPU üzerinde transkripsiyon yapılıyor…")
                collected, detected_language = transcribe_all(model)
            if cancel.is_set():
                raise TranscriptionCancelled()
            progress(100, "Tamamlandı")
            return collected, detected_language
        finally:
            if audio_path is not None:
                audio_path.unlink(missing_ok=True)
