"""Regenerate the three voice prompts in public/audio/ using macOS `say`.

Why `say` instead of gTTS: gTTS is monotone and robotic. macOS `say` with
the Samantha voice (the Siri voice) is much more natural and warmer,
which kid pilots have liked better. Output goes to .m4a (AAC) which all
modern browsers support; mp3 isn't a direct `say` output and we don't
ship ffmpeg.

Run from repo root:
    python3 scripts/generate_tts.py

Override the voice with VOICE=<name>, e.g.:
    VOICE='Karen' python3 scripts/generate_tts.py     # Australian
    VOICE='Junior' python3 scripts/generate_tts.py    # built-in kid voice
    VOICE='Nathan (Enhanced)' python3 scripts/generate_tts.py
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "public" / "audio"

VOICE = os.environ.get("VOICE", "Samantha")
RATE = int(os.environ.get("RATE", "175"))  # words per minute

PROMPTS = {
    "welcome": "Hi friend! I'm Zorpie! Let's play a super fun shape game together!",
    "how_to_play": "Look! Two pictures are the same. One is different. Tap the one that's different!",
    "reminder": "You're doing great! Tap the one that's different!",
}

OUT.mkdir(parents=True, exist_ok=True)
print(f"voice={VOICE!r}  rate={RATE}wpm  out={OUT}")

for name, text in PROMPTS.items():
    with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp:
        aiff_path = tmp.name
    m4a_path = OUT / f"{name}.m4a"
    subprocess.run(
        ["say", "-v", VOICE, "-r", str(RATE), "-o", aiff_path, text],
        check=True,
    )
    subprocess.run(
        ["afconvert", "-f", "mp4f", "-d", "aac", aiff_path, str(m4a_path)],
        check=True,
    )
    os.unlink(aiff_path)
    # Clean up any stale .mp3 with the same stem so the loader doesn't
    # accidentally pick up the old gTTS file.
    stale = OUT / f"{name}.mp3"
    if stale.exists():
        stale.unlink()
    print(f"  wrote {m4a_path}: {text!r}")
