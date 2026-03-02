"""Audio assembly — concatenate WAV chunks into M4B audiobook."""

import os
import re
import subprocess
import wave

from errors import PipelineError

MAX_CUE_CHARS = 200
MIN_CUE_DURATION = 0.3


def concat_to_m4b(wav_files: list[str], output_path: str, title: str) -> None:
    """Concatenate WAV chunks into a single M4B audiobook.

    Uses ffmpeg to concat WAVs and encode as AAC in M4B container.
    """
    if not wav_files:
        raise PipelineError("No audio chunks to combine.")

    tmpdir = os.path.dirname(wav_files[0])

    # Create ffmpeg concat list
    list_path = os.path.join(tmpdir, "filelist.txt")
    with open(list_path, "w") as f:
        for wav in wav_files:
            f.write(f"file '{wav}'\n")

    # Concat WAVs → single WAV
    combined_wav = os.path.join(tmpdir, "combined.wav")
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_path, "-c", "copy", combined_wav,
        ],
        capture_output=True, check=True,
    )

    # Convert to M4B (AAC in M4B container) with metadata
    # movflags +faststart puts the moov atom at the start for better streaming/compatibility
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", combined_wav,
            "-c:a", "aac", "-b:a", "128k",
            "-metadata", f"title={title}",
            "-metadata", "artist=A2Pod",
            "-metadata", "genre=Audiobook",
            "-movflags", "+faststart",
            "-f", "ipod", output_path,
        ],
        capture_output=True, check=True,
    )


def _split_into_segments(text: str) -> list[str]:
    """Split text into sentence-level segments for VTT cues.

    Two-level split: sentences first, then clauses for long sentences.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    segments = []
    for sentence in sentences:
        if len(sentence) <= MAX_CUE_CHARS:
            segments.append(sentence)
        else:
            # Split long sentences at clause boundaries
            parts = re.split(r"(?<=[,;])\s+|(?<=—)\s*|\s+(?=—)", sentence)
            current = ""
            for part in parts:
                if current and len(current) + len(part) + 1 > MAX_CUE_CHARS:
                    segments.append(current)
                    current = part
                else:
                    current = f"{current} {part}" if current else part
            if current:
                segments.append(current)
    return [s for s in segments if s.strip()]


def build_transcript_vtt(
    chunks: list[str], wav_files: list[str], output_path: str,
    intro_offset: float = 0.0,
) -> str:
    """Build a WebVTT transcript from text chunks and their corresponding WAV files.

    Reads each WAV's duration to produce cumulative timestamps.
    intro_offset shifts all timestamps forward to account for episode intro.
    Returns output_path.
    """
    def _fmt(seconds: float) -> str:
        h = int(seconds) // 3600
        m = (int(seconds) % 3600) // 60
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}"

    cues = []
    offset = intro_offset
    for chunk_text, wav_path in zip(chunks, wav_files):
        with wave.open(wav_path, "rb") as wf:
            duration = wf.getnframes() / wf.getframerate()
        chunk_end = offset + duration
        segments = _split_into_segments(chunk_text)
        total_chars = sum(len(s) for s in segments)
        if total_chars == 0:
            offset = chunk_end
            continue
        cursor = offset
        for i, seg in enumerate(segments):
            seg_duration = duration * len(seg) / total_chars
            seg_duration = max(seg_duration, MIN_CUE_DURATION)
            seg_end = cursor + seg_duration
            # Cap last segment to chunk boundary
            if i == len(segments) - 1 or seg_end > chunk_end:
                seg_end = chunk_end
            cues.append((cursor, seg_end, seg))
            cursor = seg_end
            if cursor >= chunk_end:
                break
        offset = chunk_end

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n")
        for start, end, text in cues:
            f.write(f"\n{_fmt(start)} --> {_fmt(end)}\n{text}\n")

    return output_path
