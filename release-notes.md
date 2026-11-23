# Release Notes -- v1.43.1

> Released: 2026-11-23

### Security

- **imagewright floor raised to 0.2.0** in `pyproject.toml`,
  `docker/requirements-image.txt` and `docker/requirements-sdxl.txt`, with the
  lock moved to match. imagewright 0.2.0 leaves `ImageConfig.api_key` out of
  the dataclass `repr()`, so printing or logging an image config no longer
  exposes the OpenAI key. It also adds `imagewright service install`; no API
  this repo uses changed.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
