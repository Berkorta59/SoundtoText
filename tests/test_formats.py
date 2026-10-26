import csv
import io
import json

import pytest

from app.core.formats import TranscriptSegment, render_transcript, timestamp


SAMPLE = [TranscriptSegment(0.5, 1.25, "Merhaba dünya."), TranscriptSegment(61.2, 63, "İyi günler.")]


def test_timestamp_formats_milliseconds_and_hours():
    assert timestamp(3661.234) == "01:01:01,234"
    assert timestamp(-1) == "00:00:00,000"


def test_export_txt_and_timestamps():
    assert render_transcript(SAMPLE, "txt") == "Merhaba dünya.\nİyi günler."
    assert render_transcript(SAMPLE[:1], "txt", include_timestamps=True) == "[00:00:00.500] Merhaba dünya."


def test_subtitle_exports_use_real_segment_times():
    srt = render_transcript(SAMPLE[:1], "srt")
    assert "1\n00:00:00,500 --> 00:00:01,250\nMerhaba dünya." in srt
    assert render_transcript(SAMPLE[:1], "vtt").startswith("WEBVTT\n\n00:00:00.500 --> 00:00:01.250")


def test_json_and_csv_are_unicode_and_parseable():
    parsed = json.loads(render_transcript(SAMPLE, "json", language="tr"))
    assert parsed["language"] == "tr"
    assert parsed["segments"][0]["text"] == "Merhaba dünya."
    rows = list(csv.reader(io.StringIO(render_transcript(SAMPLE, "csv"))))
    assert rows[1] == ["1", "0.500", "1.250", "Merhaba dünya."]


def test_unknown_export_format_is_reported():
    with pytest.raises(ValueError, match="Desteklenmeyen"):
        render_transcript(SAMPLE, "docx")
