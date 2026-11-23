# Release Notes -- v1.42.0

> Released: 2026-11-22

### Changed

- **Dependencies refreshed** (`poetry update`): 29 packages, none of them
  fleet packages. The one major move is smart-open 9.0.4 -> 10.0.0, an
  indirect dependency.

### Removed

- **The `gutenkg-image-server` and `gutenkg-sdxl-server` aliases.** Run
  `imagewright serve --backend flux` or `--backend sdxl`, as `make
  image-server`, `make sdxl-server` and the LaunchAgent already do. A
  LaunchAgent written before 1.41.0 still runs the old command; rewrite it
  with `make image-server` and then `make image-agent-install`.
  `make image-server` no longer installs this checkout into `.venv-image`,
  and `make kill`, `make down` and `make image-agent-install` stop only
  `imagewright serve`.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
