from __future__ import annotations

import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.core.media import probe_media
from app.core.transcriber import LocalTranscriber, TranscriptionCancelled


class TranscriptionWorker(QThread):
    item_status = Signal(str, str)
    item_progress = Signal(str, int, str)
    item_result = Signal(str, object)
    item_error = Signal(str, str, str)
    batch_finished = Signal(bool)
    log_message = Signal(str)

    def __init__(self, paths: list[str], settings: dict, parent=None) -> None:
        super().__init__(parent)
        self.paths = paths
        self.settings = settings
        self.cancel_event = threading.Event()
        self.transcriber = LocalTranscriber()
        self.current_path: str | None = None

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        cancelled = False
        for raw_path in self.paths:
            path = Path(raw_path)
            self.current_path = str(path)
            if self.cancel_event.is_set():
                self.item_status.emit(str(path), "İptal edildi")
                cancelled = True
                continue
            try:
                self.item_status.emit(str(path), "Hazırlanıyor")
                media = probe_media(path)
                self.item_status.emit(str(path), "Ses çıkarılıyor")

                def report(percent: float, message: str) -> None:
                    status = "Model yükleniyor" if "model" in message.lower() else (
                        "Ses çıkarılıyor" if "ses hazırlanıyor" in message.lower() else "Transkripsiyon yapılıyor"
                    )
                    self.item_status.emit(str(path), status)
                    self.item_progress.emit(str(path), int(percent), message)

                segments, language = self.transcriber.transcribe(
                    media,
                    model_name=self.settings["model"],
                    language=self.settings["language"] or None,
                    task=self.settings["task"],
                    device=self.settings["device"],
                    compute_type=self.settings["compute_type"],
                    word_timestamps=self.settings["word_timestamps"],
                    cancel=self.cancel_event,
                    progress=report,
                )
                self.item_result.emit(
                    str(path),
                    {"segments": segments, "language": language, "duration": media.duration},
                )
                self.item_status.emit(str(path), "Tamamlandı")
                self.log_message.emit(f"Tamamlandı: {path.name}")
            except TranscriptionCancelled:
                self.item_status.emit(str(path), "İptal edildi")
                cancelled = True
            except Exception as error:
                self.item_status.emit(str(path), "Hata oluştu")
                self.item_error.emit(str(path), str(error), traceback.format_exc())
                self.log_message.emit(f"Hata: {path.name} — {error}")
        self.batch_finished.emit(cancelled)
