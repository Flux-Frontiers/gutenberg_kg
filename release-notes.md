# Release Notes -- v1.43.0

> Released: 2026-11-23

### Changed

- **The worker's image synthesizer is imagewright's.** `serve/handler.py`
  builds it with `imagewright.ImageSynthesizer` and resolves a per-request
  `image_backend` itself, with the same environment variables and fallbacks
  as before. It no longer uses `kg_utils.synthesis`'s image half, which is
  due to be removed from kgmodule-utils.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
