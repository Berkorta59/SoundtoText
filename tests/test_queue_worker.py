from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.workers.transcription_worker import TranscriptionWorker


def test_worker_continues_after_per_file_error(tmp_path: Path):
    first, second = tmp_path / "first.mp3", tmp_path / "second.mp3"
    worker = TranscriptionWorker([str(first), str(second)], {})
    seen = []
    worker.item_status.connect(lambda path, status: seen.append((Path(path).name, status)))
    worker.item_error.connect(lambda path, *_: seen.append((Path(path).name, "reported-error")))
    with patch(
        "app.workers.transcription_worker.probe_media",
        side_effect=[ValueError("broken"), SimpleNamespace(duration=3.0)],
    ), patch.object(
        worker.transcriber, "transcribe", return_value=([], "tr")
    ):
        worker.settings = {
            "model": "base",
            "language": "tr",
            "task": "transcribe",
            "device": "cpu",
            "compute_type": "int8",
            "word_timestamps": False,
        }
        worker.run()
    assert ("first.mp3", "reported-error") in seen
    assert ("second.mp3", "Tamamlandı") in seen


def test_worker_marks_cancelled_pending_items(tmp_path: Path):
    paths = [str(tmp_path / "a.mp3"), str(tmp_path / "b.mp3")]
    worker = TranscriptionWorker(paths, {})
    worker.cancel()
    statuses = []
    worker.item_status.connect(lambda path, status: statuses.append(status))
    worker.run()
    assert statuses == ["İptal edildi", "İptal edildi"]
