"""Audio assembly — concatenate WAV chunks into M4B audiobook."""

import os
import subprocess
import sys


def concat_to_m4b(wav_files: list[str], output_path: str, title: str) -> None:
    """Concatenate WAV chunks into a single M4B audiobook.

    Uses ffmpeg to concat WAVs and encode as AAC in M4B container.
    """
    if not wav_files:
        print("❌ No audio chunks to combine.")
        sys.exit(1)

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

    print(" done")


