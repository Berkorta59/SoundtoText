import threading
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.media import SUPPORTED_EXTENSIONS, format_duration, format_size, probe_media, validate_media_path
from app.core.transcriber import LocalTranscriber


def test_supported_formats_include_audio_and_video():
    assert {".mp3", ".mp4", ".flac", ".mkv"} <= SUPPORTED_EXTENSIONS


def test_validate_media_path_rejects_unknown_extension(tmp_path: Path):
    media = tmp_path / "speech.xyz"
    media.write_text("not media")
    with pytest.raises(ValueError, match="Desteklenmeyen"):
        validate_media_path(media)


def test_validate_media_path_rejects_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        validate_media_path(tmp_path / "missing.mp3")


def test_format_helpers():
    assert format_duration(3661) == "01:01:01"
    assert format_size(1024) == "1.0 KB"


def test_ffmpeg_audio_preparation_uses_temporary_wav(tmp_path: Path):
    source = tmp_path / "silence.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 1600)
    media = probe_media(source)
    extracted = LocalTranscriber._extract_audio(media, threading.Event())
    try:
        with wave.open(str(extracted), "rb") as converted:
            assert converted.getnchannels() == 1
            assert converted.getframerate() == 16000
            assert converted.getnframes() > 0
    finally:
        extracted.unlink(missing_ok=True)


def test_automatic_model_selection_falls_back_to_cpu_on_missing_cublas():
    import faster_whisper

    progress = []
    model = object()
    with patch("app.core.transcriber.available_cuda_devices", return_value=1), patch.object(
        faster_whisper,
        "WhisperModel",
        side_effect=[
            RuntimeError("Library cublas64_12.dll is not found or cannot be loaded"),
            model,
        ],
    ) as whisper_model:
        transcriber = LocalTranscriber()
        loaded = transcriber._load_model("base", "auto", "auto", lambda _percent, message: progress.append(message))

    assert loaded is model
    assert transcriber._model_key == ("base", "cpu", "int8")
    assert whisper_model.call_args.kwargs["device"] == "cpu"
    assert "CPU ile devam ediliyor" in progress[1]


def test_explicit_cuda_error_explains_how_to_switch_to_cpu():
    import faster_whisper

    with patch("app.core.transcriber.available_cuda_devices", return_value=1), patch.object(
        faster_whisper,
        "WhisperModel",
        side_effect=RuntimeError("Library cublas64_12.dll is not found or cannot be loaded"),
    ):
        with pytest.raises(RuntimeError, match="Otomatik ya da İşlemci"):
            LocalTranscriber()._load_model("base", "cuda", "float16", lambda *_: None)


def test_automatic_model_retries_cpu_when_cuda_fails_during_inference(tmp_path: Path):
    class BrokenCudaModel:
        def transcribe(self, *_args, **_kwargs):
            def fail():
                raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
                yield

            return fail(), SimpleNamespace(language="en")

    class WorkingCpuModel:
        def transcribe(self, *_args, **_kwargs):
            return iter([SimpleNamespace(start=0.0, end=1.0, text=" local result ")]), SimpleNamespace(language="en")

    transcriber = LocalTranscriber()
    transcriber._model = BrokenCudaModel()
    transcriber._model_key = ("base", "cuda", "float16")
    events = []
    with patch.object(LocalTranscriber, "_extract_audio", return_value=tmp_path / "audio.wav"), patch.object(
        transcriber, "_load_model", side_effect=[BrokenCudaModel(), WorkingCpuModel()]
    ) as load_model:
        segments, language = transcriber.transcribe(
            SimpleNamespace(path=tmp_path / "source.mp3", duration=1),
            model_name="base",
            language=None,
            task="transcribe",
            device="auto",
            compute_type="auto",
            word_timestamps=False,
            cancel=threading.Event(),
            progress=lambda _percent, message: events.append(message),
        )

    assert load_model.call_args_list[1].args[:3] == ("base", "cpu", "int8")
    assert [(segment.text, language) for segment in segments] == [("local result", "en")]
    assert any("CPU ile yeniden deneniyor" in message for message in events)
