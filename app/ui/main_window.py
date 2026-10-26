from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton, QSplitter,
    QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from app.core.formats import TranscriptSegment, render_transcript
from app.core.languages import WHISPER_LANGUAGES, language_options
from app.core.media import format_duration, format_size, probe_media
from app.core.transcriber import available_cuda_devices, model_cache_path
from app.ui.translations import LANGUAGE_NAMES, UI_LANGUAGES, translate
from app.workers.transcription_worker import TranscriptionWorker

LOGGER = logging.getLogger("soundtotext")
STATUS_COLORS = {
    "Bekliyor": "#91a0b7", "Hazırlanıyor": "#e5b75b", "Ses çıkarılıyor": "#e5b75b",
    "Model yükleniyor": "#e5b75b", "Transkripsiyon yapılıyor": "#69a9ff",
    "Tamamlandı": "#55d6a2", "İptal edildi": "#a5aec0", "Hata oluştu": "#ff7272",
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings("SoundtoText", "LocalWhisper")
        self.jobs: dict[str, dict] = {}
        self.results: dict[str, dict] = {}
        self.worker: TranscriptionWorker | None = None
        self.ui_language = "tr"
        self._text_bindings: list[tuple[object, str, str, dict[str, object]]] = []
        self._tab_bindings: list[tuple[int, str]] = []
        self._combo_bindings: list[tuple[QComboBox, list[tuple[int, str]]]] = []
        self._status_message_key: str | None = None
        self._status_message_values: dict[str, object] = {}
        self._progress_message: str | None = None
        self._progress_percent = 0
        self._build_ui()
        self._load_settings()
        self.locale_combo.currentIndexChanged.connect(self._application_language_changed)
        self._retranslate_ui()
        self._update_model_state()

    def _build_ui(self) -> None:
        self._bind_text(self, "SoundtoText · Yerel Transkripsiyon", "setWindowTitle")
        self.setMinimumSize(1040, 720)
        self.setAcceptDrops(True)

        root = QWidget()
        page = QVBoxLayout(root)
        page.setContentsMargins(28, 24, 28, 24)
        page.setSpacing(18)
        hero = QHBoxLayout()
        branding = QVBoxLayout()
        title = QLabel("SoundtoText")
        title.setObjectName("appTitle")
        tagline = self._label("Sesiniz metne dönüşsün. Tamamen bu bilgisayarda.")
        tagline.setObjectName("muted")
        branding.addWidget(title)
        branding.addWidget(tagline)
        hero.addLayout(branding)
        hero.addStretch()
        self.privacy_badge = self._label("●  YEREL İŞLEME")
        self.privacy_badge.setObjectName("privacyBadge")
        hero.addWidget(self.privacy_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        page.addLayout(hero)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._make_queue_tab(), "")
        self._tab_bindings.append((0, "Transkripsiyon"))
        self.tabs.addTab(self._make_settings_tab(), "")
        self._tab_bindings.append((1, "Ayarlar"))
        self.tabs.addTab(self._make_log_tab(), "")
        self._tab_bindings.append((2, "Günlük"))
        page.addWidget(self.tabs, 1)

        footer = self._label("Dosyalarınız ve transkripsiyonlarınız hiçbir transkripsiyon servisine gönderilmez.")
        footer.setObjectName("muted")
        page.addWidget(footer)
        self.setCentralWidget(root)

    def _make_queue_tab(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 16, 12, 8)
        layout.setSpacing(14)

        actions = QHBoxLayout()
        self.add_button = self._button("＋  Dosya ekle")
        self.add_button.setObjectName("primary")
        self.add_button.clicked.connect(self._choose_files)
        self.remove_button = self._button("Seçileni kaldır")
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_button = self._button("Kuyruğu temizle")
        self.clear_button.clicked.connect(self._clear_queue)
        actions.addWidget(self.add_button)
        actions.addWidget(self.remove_button)
        actions.addWidget(self.clear_button)
        actions.addStretch()
        self.start_button = self._button("▶  Kuyruğu başlat")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self._start_queue)
        actions.addWidget(self.start_button)
        self.cancel_button = self._button("İptal")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel_queue)
        actions.addWidget(self.cancel_button)
        layout.addLayout(actions)

        self.queue_table = QTableWidget(0, 5)
        self.queue_header_keys = ("Dosya", "Biçim", "Süre", "Boyut", "Durum")
        self.queue_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.queue_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.queue_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.queue_table.verticalHeader().setVisible(False)
        self.queue_table.horizontalHeader().setStretchLastSection(True)
        self.queue_table.horizontalHeader().setSectionResizeMode(0, self.queue_table.horizontalHeader().ResizeMode.Stretch)
        self.queue_table.itemSelectionChanged.connect(self._selection_changed)
        self.queue_table.itemDoubleClicked.connect(self._open_result)
        layout.addWidget(self.queue_table, 3)

        self.status_line = self._label("Dosyaları buraya sürükleyin veya Dosya ekle'yi seçin.")
        self.status_line.setObjectName("muted")
        layout.addWidget(self.status_line)
        self.current_progress = QProgressBar()
        self.current_progress.setFormat("%p%  ·  %m")
        self.current_progress.setMaximum(100)
        layout.addWidget(self.current_progress)
        self.batch_progress = QProgressBar()
        self.batch_progress.setObjectName("batchProgress")
        self._bind_text(self.batch_progress, "Kuyruk  %p%", "setFormat")
        layout.addWidget(self.batch_progress)

        result_header = QHBoxLayout()
        result_title = self._label("Transkripsiyon sonucu")
        result_title.setObjectName("sectionTitle")
        result_header.addWidget(result_title)
        result_header.addStretch()
        result_header.addWidget(self._label("Bul:"))
        self.search_input = QLineEdit()
        self._bind_text(self.search_input, "Metinde ara…", "setPlaceholderText")
        self.search_input.setMaximumWidth(220)
        self.search_input.textChanged.connect(self._search_text)
        result_header.addWidget(self.search_input)
        result_header.addWidget(self._label("Dışa aktar:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(("TXT", "SRT", "VTT", "JSON", "CSV"))
        result_header.addWidget(self.format_combo)
        self.timestamp_checkbox = self._checkbox("TXT'de zaman damgası")
        self.timestamp_checkbox.setChecked(False)
        result_header.addWidget(self.timestamp_checkbox)
        self.save_button = self._button("Kaydet")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save_result)
        result_header.addWidget(self.save_button)
        layout.addLayout(result_header)
        self.result_info = self._label("Tamamlanan bir dosyanın sonucunu burada görüntüleyebilirsiniz.")
        self.result_info.setObjectName("muted")
        layout.addWidget(self.result_info)
        self.result_editor = QTextEdit()
        self._bind_text(
            self.result_editor,
            "Transkripsiyon metni burada görünür; metni düzenleyebilir veya kopyalayabilirsiniz.",
            "setPlaceholderText",
        )
        self.result_editor.setObjectName("resultEditor")
        layout.addWidget(self.result_editor, 2)
        return panel

    def _make_settings_tab(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 24, 24, 16)
        layout.setSpacing(18)

        model_card = QFrame()
        model_card.setObjectName("card")
        model_layout = QGridLayout(model_card)
        model_layout.setContentsMargins(18, 16, 18, 16)
        model_layout.addWidget(self._label("Whisper modeli"), 0, 0)
        self.model_combo = QComboBox()
        self._add_translated_items(self.model_combo, (
            ("tiny  ·  en hızlı, daha az doğru", "tiny"),
            ("base  ·  dengeli başlangıç", "base"),
            ("small  ·  daha doğru, daha yavaş", "small"),
            ("medium  ·  yüksek bellek / uzun süre", "medium"),
            ("large-v3  ·  en yüksek kaynak ihtiyacı", "large-v3"),
        ))
        self.model_combo.setCurrentIndex(1)
        self.model_combo.currentIndexChanged.connect(self._update_model_state)
        model_layout.addWidget(self.model_combo, 0, 1)
        model_layout.addWidget(self._label("Dil"), 1, 0)
        self.language_combo = QComboBox()
        for label, code in language_options():
            self.language_combo.addItem(label, code)
        model_layout.addWidget(self.language_combo, 1, 1)
        model_layout.addWidget(self._label("Görev"), 2, 0)
        self.task_combo = QComboBox()
        self._add_translated_items(self.task_combo, (
            ("Konuşmayı yazıya dök", "transcribe"),
            ("İngilizceye çevir", "translate"),
        ))
        model_layout.addWidget(self.task_combo, 2, 1)
        model_layout.addWidget(self._label("İşlem aygıtı"), 3, 0)
        self.device_combo = QComboBox()
        self._add_translated_items(self.device_combo, (
            ("Otomatik (önerilen)", "auto"),
            ("İşlemci (CPU)", "cpu"),
            ("NVIDIA CUDA", "cuda"),
        ))
        self.device_combo.model().item(2).setEnabled(available_cuda_devices() > 0)
        model_layout.addWidget(self.device_combo, 3, 1)
        model_layout.addWidget(self._label("Hesaplama hassasiyeti"), 4, 0)
        self.compute_combo = QComboBox()
        self._add_translated_items(self.compute_combo, (
            ("Otomatik (CPU: int8, CUDA: float16)", "auto"),
            ("int8 (daha az bellek)", "int8"),
            ("float16 (uyumlu GPU)", "float16"),
        ))
        model_layout.addWidget(self.compute_combo, 4, 1)
        self.word_timestamps = self._checkbox("Kelime düzeyinde zaman damgaları (daha yavaş)")
        model_layout.addWidget(self.word_timestamps, 5, 0, 1, 2)
        speaker_note = self._label("Konuşmacı ayrıştırma bu sürümde desteklenmiyor; yanıltıcı bir seçenek sunulmaz.")
        speaker_note.setObjectName("muted")
        model_layout.addWidget(speaker_note, 6, 0, 1, 2)
        self.model_status = QLabel()
        self.model_status.setObjectName("muted")
        model_layout.addWidget(self.model_status, 7, 0, 1, 2)
        self.cache_label = self._label("Model önbelleği: {path}", path=model_cache_path())
        self.cache_label.setWordWrap(True)
        self.cache_label.setObjectName("muted")
        model_layout.addWidget(self.cache_label, 8, 0, 1, 2)
        layout.addWidget(model_card)

        output_card = QFrame()
        output_card.setObjectName("card")
        output_layout = QGridLayout(output_card)
        output_layout.setContentsMargins(18, 16, 18, 16)
        output_layout.addWidget(self._label("Çıktı klasörü"), 0, 0)
        self.output_edit = QLineEdit()
        self._bind_text(self.output_edit, "Kaynak dosyanın bulunduğu klasör", "setPlaceholderText")
        output_layout.addWidget(self.output_edit, 0, 1)
        choose_output = self._button("Gözat…")
        choose_output.clicked.connect(self._choose_output)
        output_layout.addWidget(choose_output, 0, 2)
        output_layout.addWidget(self._label("Tema"), 1, 0)
        self.theme_combo = QComboBox()
        self._add_translated_items(self.theme_combo, (("Koyu", "dark"), ("Açık", "light")))
        self.theme_combo.currentIndexChanged.connect(self._apply_theme)
        output_layout.addWidget(self.theme_combo, 1, 1)
        output_layout.addWidget(self._label("Uygulama dili"), 2, 0)
        self.locale_combo = QComboBox()
        for native_name, code in UI_LANGUAGES:
            self.locale_combo.addItem(native_name, code)
        output_layout.addWidget(self.locale_combo, 2, 1)
        layout.addWidget(output_card)
        layout.addStretch()
        return panel

    def _make_log_tab(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 16, 12, 8)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self._bind_text(self.log_view, "İşlem ve hata mesajları burada görünür.", "setPlaceholderText")
        layout.addWidget(self.log_view)
        clear = self._button("Günlüğü temizle")
        clear.clicked.connect(self.log_view.clear)
        layout.addWidget(clear, 0, Qt.AlignmentFlag.AlignRight)
        return panel

    def _load_settings(self) -> None:
        for widget, key in (
            (self.model_combo, "model"), (self.language_combo, "language"),
            (self.task_combo, "task"), (self.device_combo, "device"),
            (self.compute_combo, "compute_type"), (self.theme_combo, "theme"),
            (self.locale_combo, "ui_language"),
        ):
            value = self.settings.value(key)
            index = widget.findData(value) if value is not None else -1
            if index >= 0:
                widget.setCurrentIndex(index)
        self.ui_language = self.locale_combo.currentData() or "tr"
        self.word_timestamps.setChecked(self.settings.value("word_timestamps", False, type=bool))
        self.output_edit.setText(self.settings.value("output_dir", "", type=str))
        self._apply_theme()

    def _save_settings(self) -> None:
        for widget, key in (
            (self.model_combo, "model"), (self.language_combo, "language"),
            (self.task_combo, "task"), (self.device_combo, "device"),
            (self.compute_combo, "compute_type"), (self.theme_combo, "theme"),
            (self.locale_combo, "ui_language"),
        ):
            self.settings.setValue(key, widget.currentData())
        self.settings.setValue("word_timestamps", self.word_timestamps.isChecked())
        self.settings.setValue("output_dir", self.output_edit.text())
        self.settings.sync()

    def _bind_text(self, widget, key: str, method: str = "setText", **values: object) -> None:
        self._text_bindings.append((widget, method, key, values))
        getattr(widget, method)(self._t(key, **values))

    def _label(self, key: str, **values: object) -> QLabel:
        label = QLabel()
        self._bind_text(label, key, **values)
        return label

    def _button(self, key: str) -> QPushButton:
        button = QPushButton()
        self._bind_text(button, key)
        return button

    def _checkbox(self, key: str) -> QCheckBox:
        checkbox = QCheckBox()
        self._bind_text(checkbox, key)
        return checkbox

    def _add_translated_items(self, combo: QComboBox, items: tuple[tuple[str, object], ...]) -> None:
        bindings = []
        for key, data in items:
            combo.addItem(self._t(key), data)
            bindings.append((combo.count() - 1, key))
        self._combo_bindings.append((combo, bindings))

    def _t(self, text: str, **values: object) -> str:
        return translate(text, self.ui_language, **values)

    def _application_language_changed(self) -> None:
        language = self.locale_combo.currentData()
        if not language:
            return
        self.ui_language = language
        self.settings.setValue("ui_language", language)
        self.settings.sync()
        self._retranslate_ui()

    def _retranslate_ui(self) -> None:
        for widget, method, key, values in self._text_bindings:
            getattr(widget, method)(self._t(key, **values))
        for index, key in self._tab_bindings:
            self.tabs.setTabText(index, f"  {self._t(key)}  ")
        for combo, bindings in self._combo_bindings:
            for index, key in bindings:
                combo.setItemText(index, self._t(key))
        names = dict(WHISPER_LANGUAGES)
        locale_names = LANGUAGE_NAMES.get(self.ui_language, {})
        for index in range(self.language_combo.count()):
            code = self.language_combo.itemData(index)
            if code == "":
                label = self._t("Otomatik algıla")
            else:
                label = locale_names.get(code, names.get(code, self.language_combo.itemText(index)))
            self.language_combo.setItemText(index, label)
        self.queue_table.setHorizontalHeaderLabels(
            tuple(self._t(key) for key in self.queue_header_keys)
        )
        for path, job in self.jobs.items():
            row = self._row_for(path)
            if row >= 0:
                self.queue_table.item(row, 4).setText(self._t(job["status"]))
        if self._status_message_key:
            self.status_line.setText(
                self._t(self._status_message_key, **self._status_message_values)
            )
        if self._progress_message:
            self._update_progress_display()
        if self.worker is None:
            self._update_model_state()
        active_path = getattr(self, "active_result_path", None)
        if active_path in self.results:
            self._update_result_info(active_path)
        self.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if self.ui_language == "ar"
            else Qt.LayoutDirection.LeftToRight
        )

    def _apply_theme(self) -> None:
        theme = self.theme_combo.currentData() or "dark"
        if theme == "light":
            self.setStyleSheet(LIGHT_STYLE)
        else:
            self.setStyleSheet(DARK_STYLE)

    def _update_model_state(self) -> None:
        model = self.model_combo.currentData() if hasattr(self, "model_combo") else "base"
        downloaded = (model_cache_path() / f"models--Systran--faster-whisper-{model}").is_dir()
        state = "İndirildi" if downloaded else "İlk kullanımda indirilecek"
        self.model_status.setText(self._t("Seçili model: {model} · {state}", model=model, state=self._t(state)))

    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, self._t("Ses veya video dosyaları ekle"), str(Path.home()),
            f"{self._t('Medya dosyaları')} (*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma *.mp4 *.mkv *.mov *.avi *.webm *.m4v);;{self._t('Tüm dosyalar')} (*)",
        )
        self._add_files(paths)

    def _add_files(self, paths: list[str]) -> None:
        added = 0
        for raw in paths:
            path = str(Path(raw).resolve())
            if path in self.jobs:
                continue
            try:
                media = probe_media(path)
            except Exception as error:
                self._log(self._t("Dosya eklenemedi ({name}): {error}", name=Path(path).name, error=error))
                QMessageBox.warning(
                    self, self._t("Dosya eklenemedi"),
                    self._t("Dosya eklenemedi:\n{name}\n\n{error}", name=Path(path).name, error=error),
                )
                continue
            self.jobs[path] = {"duration": media.duration, "status": "Bekliyor", "progress": 0}
            self._append_job_row(path, media)
            added += 1
        if added:
            self._set_status_message("{count} dosya kuyruğa eklendi. Başlatmaya hazır.", count=added)
            self._log(self._t("{count} dosya kuyruğa eklendi.", count=added))
        self._selection_changed()

    def _append_job_row(self, path: str, media) -> None:
        row = self.queue_table.rowCount()
        self.queue_table.insertRow(row)
        values = (Path(path).name, Path(path).suffix[1:].upper(), format_duration(media.duration),
                  format_size(media.size_bytes), self._t("Bekliyor"))
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setData(Qt.ItemDataRole.UserRole, path)
            if column == 4:
                item.setForeground(Qt.GlobalColor.gray)
            self.queue_table.setItem(row, column, item)

    def _selected_paths(self) -> list[str]:
        rows = sorted({index.row() for index in self.queue_table.selectedIndexes()})
        return [self.queue_table.item(row, 0).data(Qt.ItemDataRole.UserRole) for row in rows]

    def _remove_selected(self) -> None:
        if self.worker:
            return
        for row in sorted({index.row() for index in self.queue_table.selectedIndexes()}, reverse=True):
            path = self.queue_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            self.jobs.pop(path, None)
            self.queue_table.removeRow(row)
        self._selection_changed()

    def _clear_queue(self) -> None:
        if self.worker:
            return
        self.jobs.clear()
        self.results.clear()
        self.queue_table.setRowCount(0)
        self.result_editor.clear()
        self.result_info.setText(self._t("Tamamlanan bir dosyanın sonucunu burada görüntüleyebilirsiniz."))
        self.save_button.setEnabled(False)
        self.current_progress.setValue(0)
        self.batch_progress.setValue(0)
        self._selection_changed()

    def _selection_changed(self) -> None:
        selected = self._selected_paths()
        self.remove_button.setEnabled(bool(selected) and self.worker is None)
        self.start_button.setEnabled(self.worker is None and bool(self.jobs))
        if len(selected) == 1 and selected[0] in self.results:
            self._show_result(selected[0])

    def _start_queue(self) -> None:
        paths = self._selected_paths() or [
            path for path, job in self.jobs.items() if job["status"] not in ("Tamamlandı", "Hata oluştu")
        ]
        if not paths:
            QMessageBox.information(
                self, self._t("Kuyruk boş"), self._t("Önce işlenecek bir dosya seçin.")
            )
            return
        self._status_message_key = None
        self._save_settings()
        settings = {
            "model": self.model_combo.currentData(),
            "language": self.language_combo.currentData(),
            "task": self.task_combo.currentData(),
            "device": self.device_combo.currentData(),
            "compute_type": self.compute_combo.currentData(),
            "word_timestamps": self.word_timestamps.isChecked(),
        }
        for path in paths:
            self.jobs[path]["progress"] = 0
            if self.jobs[path]["status"] in ("Hata oluştu", "İptal edildi", "Tamamlandı"):
                self.jobs[path]["status"] = "Bekliyor"
                self._set_status(path, "Bekliyor")
        self.current_paths = paths
        self.finished_count = 0
        self.batch_progress.setValue(0)
        self.worker = TranscriptionWorker(paths, settings, self)
        self.worker.item_status.connect(self._set_status)
        self.worker.item_progress.connect(self._set_progress)
        self.worker.item_result.connect(self._result_received)
        self.worker.item_error.connect(self._error_received)
        self.worker.log_message.connect(self._log)
        self.worker.batch_finished.connect(self._batch_finished)
        self.worker.finished.connect(self._worker_stopped)
        self._set_running(True)
        self.worker.start()
        self._log(self._t("{count} dosya için yerel transkripsiyon başlatıldı.", count=len(paths)))

    def _set_running(self, running: bool) -> None:
        self.add_button.setEnabled(not running)
        self.remove_button.setEnabled(not running)
        self.clear_button.setEnabled(not running)
        self.start_button.setEnabled(not running and bool(self.jobs))
        self.cancel_button.setEnabled(running)
        self.model_combo.setEnabled(not running)
        self.language_combo.setEnabled(not running)
        self.task_combo.setEnabled(not running)
        self.device_combo.setEnabled(not running)
        self.compute_combo.setEnabled(not running)
        self.word_timestamps.setEnabled(not running)

    def _cancel_queue(self) -> None:
        if self.worker:
            self.cancel_button.setEnabled(False)
            self._set_status_message(
                "İptal isteği gönderildi; geçerli güvenli işlem adımının bitmesi bekleniyor…"
            )
            self.worker.cancel()

    def _set_status(self, path: str, status: str) -> None:
        if path in self.jobs:
            self.jobs[path]["status"] = status
        row = self._row_for(path)
        if row >= 0:
            item = self.queue_table.item(row, 4)
            item.setText(self._t(status))
            item.setForeground(self._color(STATUS_COLORS.get(status, "#91a0b7")))
        if self.worker and path == self.worker.current_path:
            self._set_status_message("{name} · {status}", name=Path(path).name, status=status)
        if status in ("Tamamlandı", "Hata oluştu", "İptal edildi") and hasattr(self, "current_paths"):
            self.finished_count += 1
            self.batch_progress.setValue(int(self.finished_count / max(1, len(self.current_paths)) * 100))

    def _set_progress(self, path: str, percent: int, message: str) -> None:
        self._progress_message = message
        self._progress_percent = percent
        if path in self.jobs:
            self.jobs[path]["progress"] = percent
        self._set_status_message("{name} · {message}", name=Path(path).name, message=self._localized_progress(message))
        self._update_progress_display()

    def _update_progress_display(self) -> None:
        if not self._progress_message:
            return
        message = self._progress_message
        if "model" in message.lower() and "yükleniyor" in message.lower():
            self.current_progress.setRange(0, 0)
            self.current_progress.setFormat(self._localized_progress(message))
        else:
            self.current_progress.setRange(0, 100)
            self.current_progress.setValue(self._progress_percent)
            self.current_progress.setFormat(f"{self._progress_percent}%  ·  {self._localized_progress(message)}")

    def _localized_progress(self, message: str) -> str:
        suffix = " modeli yükleniyor; ilk kullanımda indirilebilir…"
        if message.endswith(suffix):
            model_name = message[:-len(suffix)]
            return self._t(
                "Model {model} is loading; it may be downloaded on first use…",
                model=model_name,
            )
        return self._t(message)

    def _set_status_message(self, key: str, **values: object) -> None:
        self._status_message_key = key
        self._status_message_values = values
        self.status_line.setText(self._t(key, **values))

    def _result_received(self, path: str, payload: dict) -> None:
        self.results[path] = payload
        self._log(self._t(
            "Sonuç hazır: {name} · dil: {language}",
            name=Path(path).name,
            language=payload["language"] or self._t("belirtilmedi"),
        ))
        self._show_result(path)

    def _show_result(self, path: str) -> None:
        result = self.results.get(path)
        if not result:
            return
        segments: list[TranscriptSegment] = result["segments"]
        self.result_editor.setPlainText(render_transcript(segments, "txt"))
        self._update_result_info(path)
        self.active_result_path = path
        self.save_button.setEnabled(True)
        self._search_text(self.search_input.text())

    def _update_result_info(self, path: str) -> None:
        result = self.results[path]
        language_code = result["language"]
        language = self._language_name_for_code(language_code) if language_code else self._t("belirtilmedi")
        self.result_info.setText(self._t(
            "{name}   ·   {duration}   ·   {count} bölüm   ·   Algılanan dil: {language}",
            name=Path(path).name,
            duration=format_duration(result["duration"]),
            count=len(result["segments"]),
            language=language,
        ))

    def _language_name_for_code(self, code: str) -> str:
        featured_name = LANGUAGE_NAMES.get(self.ui_language, {}).get(code)
        if featured_name:
            return featured_name
        names = dict(WHISPER_LANGUAGES)
        return names.get(code, code)

    def _save_result(self) -> None:
        path = getattr(self, "active_result_path", None)
        if not path or path not in self.results:
            return
        extension = self.format_combo.currentText().lower()
        base_dir = self.output_edit.text().strip() or str(Path(path).parent)
        output = Path(base_dir) / f"{Path(path).stem}.{extension}"
        source = self.results[path]
        if extension == "txt":
            content = self.result_editor.toPlainText()
            if self.timestamp_checkbox.isChecked():
                edited_segments = self._edited_segments(source["segments"])
                if edited_segments is None:
                    QMessageBox.warning(
                        self, self._t("Zaman damgaları eklenemedi"),
                        self._t(
                            "Düzenlenmiş satır sayısı segment sayısıyla eşleşmiyor. "
                            "Satır sayısını koruyun veya TXT zaman damgalarını kapatın."
                        ),
                    )
                    return
                content = render_transcript(edited_segments, "txt", include_timestamps=True)
        else:
            edited_segments = self._edited_segments(source["segments"])
            if edited_segments is None:
                QMessageBox.warning(
                    self, self._t("Zaman bilgisi eşleştirilemiyor"),
                    self._t(
                        "SRT, VTT, JSON ve CSV için düzenlenmiş satır sayısı segment sayısıyla "
                        "aynı olmalıdır. Metin olarak kaydetmek için TXT seçin."
                    ),
                )
                return
            content = render_transcript(edited_segments, extension, language=source["language"])
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            candidate = output
            index = 1
            while True:
                try:
                    with candidate.open("x", encoding="utf-8", newline="") as output_file:
                        output_file.write(content)
                    break
                except FileExistsError:
                    candidate = output.with_name(f"{output.stem} ({index}){output.suffix}")
                    index += 1
        except OSError as error:
            QMessageBox.critical(
                self, self._t("Kaydetme hatası"),
                self._t("Dosya kaydedilemedi:\n{path}\n\n{error}", path=candidate, error=error),
            )
            self._log(self._t("Kaydetme hatası ({name}): {error}", name=candidate.name, error=error))
            return
        self._log(self._t("Sonuç kaydedildi: {path}", path=candidate))
        QMessageBox.information(
            self, self._t("Dışa aktarıldı"),
            self._t("Transkripsiyon kaydedildi:\n{path}", path=candidate),
        )

    def _edited_segments(self, segments: list[TranscriptSegment]) -> list[TranscriptSegment] | None:
        from dataclasses import replace

        lines = [line.strip() for line in self.result_editor.toPlainText().splitlines()]
        if len(lines) != len(segments):
            return None
        return [replace(segment, text=line) for segment, line in zip(segments, lines)]

    def _error_received(self, path: str, message: str, details: str) -> None:
        LOGGER.error("Transkripsiyon hatası: %s\n%s", Path(path).name, details)
        self._log(self._t("Teknik ayrıntı: {message}", message=message))
        QMessageBox.warning(
            self, self._t("Transkripsiyon hatası"),
            self._t("Dosya eklenemedi:\n{name}\n\n{error}", name=Path(path).name, error=message),
        )

    def _batch_finished(self, cancelled: bool) -> None:
        self._set_status_message(
            "Kuyruk iptal edildi." if cancelled else "Kuyruktaki işlem tamamlandı."
        )

    def _worker_stopped(self) -> None:
        worker = self.worker
        self.worker = None
        self.current_progress.setRange(0, 100)
        self._update_model_state()
        self._set_running(False)
        if worker:
            worker.deleteLater()
        self._selection_changed()

    def _row_for(self, path: str) -> int:
        for row in range(self.queue_table.rowCount()):
            if self.queue_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == path:
                return row
        return -1

    def _search_text(self, query: str) -> None:
        if not query:
            return
        cursor = self.result_editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        found = self.result_editor.document().find(query, cursor)
        if not found.isNull():
            self.result_editor.setTextCursor(found)
            self.result_editor.ensureCursorVisible()

    def _choose_output(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, self._t("Çıktı klasörünü seç"))
        if directory:
            self.output_edit.setText(directory)
            self._save_settings()

    def _open_result(self, item: QTableWidgetItem) -> None:
        path = self.queue_table.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
        if path in self.results:
            self._show_result(path)

    def _log(self, message: str) -> None:
        if hasattr(self, "log_view"):
            self.log_view.append(self._translate_log(message))

    def _translate_log(self, message: str) -> str:
        if message.startswith("Tamamlandı: "):
            return self._t("Completed: {name}", name=message[len("Tamamlandı: "):])
        if message.startswith("Hata: "):
            name, separator, error = message[len("Hata: "):].partition(" — ")
            return self._t("Error: {name} — {error}", name=name, error=error) if separator else message
        return message

    @staticmethod
    def _color(value: str):
        from PySide6.QtGui import QColor
        return QColor(value)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        self._add_files([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])

    def closeEvent(self, event) -> None:
        if self.worker:
            question = QMessageBox(self)
            question.setWindowTitle(self._t("İşlem sürüyor"))
            question.setText(
                self._t("Transkripsiyon çalışıyor. İptal edip uygulamayı kapatmak istiyor musunuz?")
            )
            yes_button = question.addButton(self._t("Evet"), QMessageBox.ButtonRole.AcceptRole)
            no_button = question.addButton(self._t("Hayır"), QMessageBox.ButtonRole.RejectRole)
            question.setDefaultButton(no_button)
            question.exec()
            if question.clickedButton() is not yes_button:
                event.ignore()
                return
            self.worker.cancel()
            self.worker.wait(5000)
            if self.worker.isRunning():
                event.ignore()
                QMessageBox.information(
                    self, self._t("Kapatma bekleniyor"),
                    self._t("Güvenli iptal tamamlanınca uygulamayı kapatabilirsiniz."),
                )
                return
        self._save_settings()
        event.accept()


DARK_STYLE = """
QWidget { background: #111722; color: #e8edf5; font-family: "Segoe UI"; font-size: 10pt; }
QTabWidget::pane { border: 1px solid #283346; border-radius: 12px; background: #171f2c; }
QTabBar::tab { background: #131b27; color: #9eacc0; padding: 11px 18px; margin-right: 5px; border-radius: 8px; }
QTabBar::tab:selected { color: #fff; background: #293a54; }
QLabel#appTitle { font-size: 25pt; font-weight: 700; color: #f4f7fc; }
QLabel#sectionTitle { font-size: 13pt; font-weight: 650; }
QLabel#muted { color: #96a4b8; }
QLabel#privacyBadge { background: #123c35; color: #74e0b6; border: 1px solid #286352; border-radius: 12px; padding: 8px 12px; font-weight: 700; }
QFrame#card { background: #1b2533; border: 1px solid #2a3749; border-radius: 12px; }
QPushButton { background: #273346; border: 1px solid #35445a; border-radius: 8px; padding: 9px 14px; }
QPushButton:hover { background: #34455d; }
QPushButton:disabled { color: #69778b; background: #202a38; }
QPushButton#primary { background: #3979d5; border-color: #4b8be8; color: white; font-weight: 650; }
QPushButton#primary:hover { background: #4b8be8; }
QLineEdit, QComboBox, QTextEdit, QTableWidget { background: #131b27; border: 1px solid #2c394b; border-radius: 7px; padding: 7px; selection-background-color: #3979d5; }
QComboBox QAbstractItemView { background: #1b2533; selection-background-color: #3979d5; }
QTableWidget { gridline-color: #283346; }
QHeaderView::section { background: #1c2634; color: #aab6c7; border: none; padding: 9px; font-weight: 650; }
QProgressBar { background: #202a38; border: none; border-radius: 6px; height: 14px; text-align: center; color: #e8edf5; }
QProgressBar::chunk { background: #3e9b7b; border-radius: 6px; }
QProgressBar#batchProgress::chunk { background: #3979d5; }
QCheckBox { spacing: 8px; }
"""

LIGHT_STYLE = """
QWidget { background: #f3f6fb; color: #202b3a; font-family: "Segoe UI"; font-size: 10pt; }
QTabWidget::pane { border: 1px solid #d7deea; border-radius: 12px; background: #fff; }
QTabBar::tab { background: #e9eef6; color: #56647a; padding: 11px 18px; margin-right: 5px; border-radius: 8px; }
QTabBar::tab:selected { color: #18365d; background: #d7e6fb; }
QLabel#appTitle { font-size: 25pt; font-weight: 700; color: #17253a; }
QLabel#sectionTitle { font-size: 13pt; font-weight: 650; }
QLabel#muted { color: #66758b; }
QLabel#privacyBadge { background: #def5ec; color: #14694c; border: 1px solid #b8e5d4; border-radius: 12px; padding: 8px 12px; font-weight: 700; }
QFrame#card { background: #fff; border: 1px solid #d7deea; border-radius: 12px; }
QPushButton { background: #edf1f7; border: 1px solid #d4dce8; border-radius: 8px; padding: 9px 14px; }
QPushButton:hover { background: #dfe8f5; }
QPushButton:disabled { color: #98a3b3; }
QPushButton#primary { background: #3475d0; border-color: #3475d0; color: white; font-weight: 650; }
QPushButton#primary:hover { background: #2864b5; }
QLineEdit, QComboBox, QTextEdit, QTableWidget { background: #fff; border: 1px solid #d7deea; border-radius: 7px; padding: 7px; selection-background-color: #8fb6eb; }
QComboBox QAbstractItemView { background: #fff; selection-background-color: #cfe0f7; }
QTableWidget { gridline-color: #e1e6ee; }
QHeaderView::section { background: #eef2f8; color: #526178; border: none; padding: 9px; font-weight: 650; }
QProgressBar { background: #e5eaf1; border: none; border-radius: 6px; height: 14px; text-align: center; color: #26364c; }
QProgressBar::chunk { background: #3e9b7b; border-radius: 6px; }
QProgressBar#batchProgress::chunk { background: #3979d5; }
QCheckBox { spacing: 8px; }
"""
