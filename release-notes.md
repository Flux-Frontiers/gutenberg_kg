# Release Notes -- v1.27.1

> Released: 2026-10-20

### Changed

- **KG pin set moved to kg-rag 0.17.2 and diary-kg 0.100.1** by
  `scripts/check_pins.py --bump`, across the pyproject floors, `poetry.lock`,
  the `docker/Dockerfile` ARGs and `runpod/requirements.txt`. Both releases
  carry the pymupdf 2.0 PDF fix; neither changes the index, so the current
  bundle stays valid.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
