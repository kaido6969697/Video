# QA — The $27 Million Fake Funeral Sting

- 24-shot contact sheet rendered before the movie: `qa_contact_sheet.jpg`.
- Full MP4 decode passed with FFmpeg.
- 1920×1080 H.264, 30 fps, 209 seconds; stereo AAC, 48 kHz.
- Audio assembled at 48 kHz with tanh limiting and FFmpeg loudnorm (`I=-14`, `TP=-1.5`, `LRA=7`).
- SRT contains 27 cues generated from the production manifest and estimated clip splits.
- ASR verification could not be performed because a compatible ASR model/runtime was unavailable. Captions therefore are not claimed to be ASR-verified.
- Visuals are a Pillow-built original-art fallback (960×540 source art upscaled to 1080p); the supplied Skia EGL runtime was unavailable.
