# Repository and skill analysis

## What this repository contains

This checkout is a small archive repository: the checked-in ZIP is the only substantive original asset; the original `README.md` is a one-line stub. The ZIP was tested successfully and contains `SKILL.md`, one Eiffel Tower example, and seven Python files (`tts3.py`, `audio_mix3.py`, `lib.py`, `kit3.py`, `long.py`, `scenes3.py`, and `timeline.py`). It does **not** contain generated audio/video, model weights, or a test suite.

The skill describes a procedural 2D explainer-video pipeline: Kokoro TTS through Sherpa-ONNX, custom Skia drawing/animation, WAV mixing in NumPy/SciPy, and MP4 encoding through FFmpeg. The example is a 1:56 Eiffel Tower story, with an intro and continuation split across separate scripts.

## Installation and validation performed

- Installed the skill as `.claude/skills/2d-animation-long-form-aivxer/` (including its example files), preserving the source ZIP.
- Created a project-local Python virtual environment at `.venv/` and installed the packages in `requirements.txt`: NumPy, SciPy, SoundFile, skia-python, sherpa-onnx, and imageio-ffmpeg. The virtual environment is ignored by Git.
- Installed a usable FFmpeg executable through `imageio-ffmpeg`; `.venv/bin/ffmpeg` points to its bundled FFmpeg binary.
- Downloaded the three named Google Fonts into `~/vid/fonts/`: Caveat Brush, Kalam Bold, and Permanent Marker.
- `compileall` succeeds for every example Python file. NumPy, SciPy, SoundFile, Sherpa-ONNX, and imageio-ffmpeg import successfully.

## Original skill pipeline blockers and completed video

The archived example's **original Skia + Sherpa-ONNX pipeline remains unavailable** in this environment, but a complete video was produced using a code-based Pillow renderer, the selected English voice, and FFmpeg. The generated MP4 is `deliverables/fake_funeral_27m_scam.mp4` (1280×720, 24 fps, 3:38.84), with a separate SRT and reproducible drawing/encoding script.

The original skill-specific limitations are:

1. **Skia needs a missing system library.** Importing `skia` fails with `ImportError: libEGL.so.1: cannot open shared object file`. This is an OS-level EGL runtime (commonly provided by `libegl1` on Debian/Ubuntu), not a Python requirement. The available outbound hosts in this workspace do not include the OS package repositories, so it was not installed here. The alternate Pillow renderer avoids Skia.
2. **The two large model archives could not be downloaded.** The skill's Kokoro TTS archive is 349,886,476 bytes and the Parakeet ASR archive is 482,440,461 bytes (about 794 MiB combined). GitHub's release URLs redirect to `objects.githubusercontent.com`, which this workspace cannot reach. The `.venv` has the Sherpa-ONNX runtime but no model weights. The completed video uses the available selected voice-generation tool rather than Kokoro; ASR verification was therefore not possible.
3. **Example paths are machine-specific.** Scripts refer to `/home/claude/models` and `/home/claude/vid` for models, fonts, audio, scene output, and frame caches. The local fonts were downloaded to `~/vid/fonts`, but that does not make the other fixed `/home/claude/...` paths portable. Before using the archived scripts on another machine, update those constants or provide matching directories and files.
4. **There are runtime prerequisites beyond Python.** The archived example assumes FFmpeg with H.264 (`libx264`) encoding and expects TTS outputs, intro WAVs, timeline JSON, and rendered shot folders in a specific sequence. The README's workflow order is significant; there is no single end-to-end runner. The generated video uses the installed FFmpeg and Pillow-based renderer instead.

## Code and workflow observations

- The ZIP is intact and all supplied Python files pass syntax compilation. That is a syntax check only; the code was not executed because models, generated audio, and EGL are missing.
- The sample scripts mix reusable drawing/audio helpers with top-level execution and absolute filesystem paths. `audio_mix3.py` performs work at import/run time, and `long.py` conditionally generates audio based on CLI arguments before loading generated artifacts. This makes ad-hoc imports and isolated tests difficult.
- The project has no dependency lockfile, automated tests, model checksums, or portable path/configuration layer. The starter `requirements.txt` is therefore intentionally unpinned; pin versions after confirming the target OS/Python and render output.
- The skill's creative guidance is detailed and safety-conscious about original character design and fact-checking. For the delivered Pillow-rendered video, busy frames and the MP4 decode were checked; its synthesized voice follows the prepared script, but independent ASR transcription was unavailable because the ASR model archive could not be downloaded.

## Reproducing the remaining setup elsewhere

1. Install the OS EGL runtime (for example, `libegl1` on Debian/Ubuntu) and an FFmpeg build with `libx264` enabled.
2. From the repo root, activate `.venv` and run `pip install -r requirements.txt`.
3. Download and unpack the Kokoro and Parakeet archives at the model paths expected by the skill, and ensure the archive extracts to the exact directory names used in the scripts.
4. Change the `/home/claude/...` constants to local paths (or create those directories), then run the example in the documented sequence in `.claude/skills/2d-animation-long-form-aivxer/examples/eiffel_tower/README.md`.
5. Render selected still frames first, then render, mix audio, mux, and verify the finished result.
