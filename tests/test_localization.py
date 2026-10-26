import pytest
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow
from app.ui.translations import LANGUAGE_NAMES, UI_LANGUAGES, translate


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_interface_languages_translate_controls_and_preserve_transcription_language(qapp):
    window = MainWindow()
    contains_saved_language = window.settings.contains("ui_language")
    saved_language = window.settings.value("ui_language")
    selected_speech_language = window.language_combo.currentData()
    try:
        for native_name, code in UI_LANGUAGES:
            window.locale_combo.setCurrentIndex(window.locale_combo.findData(code))
            assert window.locale_combo.currentText() == native_name
            assert window.windowTitle() != "SoundtoText · Yerel Transkripsiyon" or code == "tr"
            assert window.tabs.tabText(0).strip() == translate("Transkripsiyon", code)
            assert window.add_button.text() == translate("＋  Dosya ekle", code)
            assert window.queue_table.horizontalHeaderItem(0).text() == translate("Dosya", code)
            assert window.settings.value("ui_language") == code
            assert window.language_combo.currentData() == selected_speech_language
            speech_turkish_index = window.language_combo.findData("tr")
            assert window.language_combo.itemText(speech_turkish_index) == LANGUAGE_NAMES.get(code, {}).get(
                "tr", "Türkçe"
            )
            if code != "tr":
                assert window._localized_progress(
                    "base modeli yükleniyor; ilk kullanımda indirilebilir…"
                ) != "base modeli yükleniyor; ilk kullanımda indirilebilir…"
            if code == "ar":
                assert window.layoutDirection().name == "RightToLeft"
            else:
                assert window.layoutDirection().name == "LeftToRight"
    finally:
        if contains_saved_language:
            window.settings.setValue("ui_language", saved_language)
        else:
            window.settings.remove("ui_language")
        window.settings.sync()
        window.hide()
        window.deleteLater()
        qapp.processEvents()


@pytest.mark.parametrize("code", [code for _name, code in UI_LANGUAGES])
def test_interface_translations_cover_all_static_screen_labels(code):
    source_text = (
        "SoundtoText · Yerel Transkripsiyon",
        "Sesiniz metne dönüşsün. Tamamen bu bilgisayarda.",
        "Transkripsiyon", "Ayarlar", "Günlük",
        "＋  Dosya ekle", "Seçileni kaldır", "Kuyruğu temizle",
        "▶  Kuyruğu başlat", "İptal", "Dosya", "Biçim", "Süre",
        "Boyut", "Durum", "Transkripsiyon sonucu", "Whisper modeli",
        "Dil", "Görev", "İşlem aygıtı", "Hesaplama hassasiyeti",
        "Uygulama dili", "Çıktı klasörü", "Günlüğü temizle",
    )
    if code != "tr":
        assert all(translate(text, code) != text for text in source_text)
