"""TTS generation using MLX Audio (Kokoro)."""

import logging
import os
import warnings

import numpy as np

MODEL = "mlx-community/Kokoro-82M-bf16"
DEFAULT_VOICE = "af_heart"
DEFAULT_SPEED = 1.0
LANG_CODE = "a"  # English
SAMPLE_RATE = 24000


def generate_audio_chunks(
    chunks: list[str],
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
    tmpdir: str = "/tmp",
    model_id: str = MODEL,
) -> list[str]:
    """Generate WAV files for each text chunk.

    Returns list of WAV file paths.
    """
    import soundfile as sf

    # Suppress noisy library output
    logging.disable(logging.WARNING)
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

    print(f"  Loading TTS model...", end="", flush=True)
    from mlx_audio.tts.utils import load_model
    model = load_model(model_id)
    print(" done")

    wav_files = []
    total = len(chunks)

    for i, chunk in enumerate(chunks, 1):
        print(f"  Generating audio [{i}/{total}]...", end="", flush=True)

        audio_segments = []
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for result in model.generate(chunk, voice=voice, speed=speed, lang_code=LANG_CODE):
                audio_segments.append(np.array(result.audio))

        if not audio_segments:
            print(" skipped (no audio)")
            continue

        audio = np.concatenate(audio_segments)
        duration = len(audio) / SAMPLE_RATE
        wav_path = os.path.join(tmpdir, f"chunk_{i:04d}.wav")
        sf.write(wav_path, audio, SAMPLE_RATE)
        wav_files.append(wav_path)
        print(f" {duration:.0f}s")

    return wav_files
