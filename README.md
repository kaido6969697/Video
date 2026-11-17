# VideoArchive

## Watch the generated video

[Open the 3:39 animated explainer (MP4)](deliverables/fake_funeral_27m_scam.mp4)

This repository contains the `2d-animation-long-form-aivxer` animation skill and its Eiffel Tower demo. The skill is installed locally under `.claude/skills/2d-animation-long-form-aivxer/`.

## Python setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
ln -sf "$(.venv/bin/python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')" .venv/bin/ffmpeg
export PATH="$PWD/.venv/bin:$PATH"
```

Running the **original archived example** additionally needs an OS EGL runtime (such as `libegl1` on Debian/Ubuntu), FFmpeg with H.264 support, and the Kokoro TTS / Parakeet ASR model archives; its scripts use fixed `/home/claude/...` paths. A separate Pillow-based code renderer creates the 25-shot version in `deliverables/`, with distinct locations, animated puppet expressions and gestures, kinetic text, animated case graphics, and wipe transitions—without those unavailable model/system dependencies.

Re-render the delivered Pillow version (the generated voice clips are already in `deliverables/`) with:

```bash
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python deliverables/create_video.py
```

See [REPO_ANALYSIS.md](REPO_ANALYSIS.md) for the full contents, install results, validation, and remaining environment blockers.
