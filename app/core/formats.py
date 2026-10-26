from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


def timestamp(seconds: float, separator: str = ",") -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02}{separator}{millis:03}"


def render_transcript(
    segments: Iterable[TranscriptSegment],
    output_format: str,
    include_timestamps: bool = False,
    language: str | None = None,
) -> str:
    items = list(segments)
    kind = output_format.lower().lstrip(".")
    if kind == "txt":
        if include_timestamps:
            return "\n".join(f"[{timestamp(item.start, '.')}] {item.text.strip()}" for item in items)
        return "\n".join(item.text.strip() for item in items).strip()
    if kind == "srt":
        return "\n\n".join(
            f"{index}\n{timestamp(item.start)} --> {timestamp(item.end)}\n{item.text.strip()}"
            for index, item in enumerate(items, 1)
        ) + ("\n" if items else "")
    if kind == "vtt":
        cues = "\n\n".join(
            f"{timestamp(item.start, '.')} --> {timestamp(item.end, '.')}\n{item.text.strip()}"
            for item in items
        )
        return "WEBVTT\n\n" + (cues + "\n" if cues else "")
    if kind == "json":
        return json.dumps(
            {"language": language, "segments": [asdict(item) for item in items]},
            ensure_ascii=False,
            indent=2,
        )
    if kind == "csv":
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(("segment", "start_seconds", "end_seconds", "text"))
        writer.writerows(
            (index, f"{item.start:.3f}", f"{item.end:.3f}", item.text)
            for index, item in enumerate(items, 1)
        )
        return output.getvalue()
    raise ValueError(f"Desteklenmeyen çıktı biçimi: {output_format}")
