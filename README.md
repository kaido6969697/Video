# The $27 Million Fake Funeral Sting

A 24-shot animated documentary in an original drawn-puppet style.

- **Finished film:** [`deliverables/fake_funeral_27m_scam.mp4`](deliverables/fake_funeral_27m_scam.mp4)
- **Captions:** [`deliverables/fake_funeral_27m_scam.srt`](deliverables/fake_funeral_27m_scam.srt)
- **Visual QA contact sheet:** [`deliverables/qa_contact_sheet.jpg`](deliverables/qa_contact_sheet.jpg)
- **QA notes:** [`deliverables/qa_report.md`](deliverables/qa_report.md)
- **Shot list:** [`deliverables/shotlist_24.md`](deliverables/shotlist_24.md)
- **Renderer:** [`deliverables/create_video.py`](deliverables/create_video.py)

The movie is 1920×1080, 30 fps, 3:29, with 48 kHz stereo AAC. Install `requirements.txt`, then run `python deliverables/create_video.py` from the repository root to rebuild it using the included voice WAVs. The renderer is a Pillow fallback; source artwork is rendered at 960×540 and upscaled to 1080p because the supplied Skia runtime is unavailable in this environment.
