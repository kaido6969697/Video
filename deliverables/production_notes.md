# Production notes — The $27 Million Fake Funeral Sting

## Format and render

- 24-shot, English-language animated documentary; 209 seconds (3:29), 1920×1080 H.264 at 30 fps.
- AAC stereo at 48 kHz; FFmpeg loudnorm target `I=-14:TP=-1.5:LRA=7`.
- Original procedural score (104 BPM, A-minor palette), synthesized dialogue, sidechain ducking, room reverb, whip/paper/gavel cues, and low chapter-card booms.
- The storyboard contact sheet was rendered before the full MP4. FFmpeg decoded the full final file without errors.
- Renderer uses original Pillow-drawn puppets and sets, then Lanczos-upscales 960×540 artwork to the 1080p deliverable; the supplied skill's Skia runtime wasn't usable in this environment.
- ASR was unavailable, so captions follow the production text and estimated clip splits rather than a transcription of the encoded audio. Please watch once to check dialogue timing.

## Fact boundaries

The film distinguishes wider-scheme losses exceeding $27 million from Jiandong Chen's admitted role-related losses exceeding $9.5 million. It states his sentence as 78 months. The viral sting is presented as one pickup within a broader investigation, not as the sole proof or cause of the prosecution.

## Skill credit

Made in the original drawn-puppet explainer style inspired by the supplied `2d-animation-long-form-aivxer` skill. Skill author credit: aivxer. Characters are original generic puppets, not real-person likenesses.
