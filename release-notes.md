# Release Notes -- v1.39.0

> Released: 2026-11-17

### Changed

- **The default model is now `Qwen3-8B-MLX-4bit`, replacing
  `Qwen3-4B-Instruct-2507-MLX-8bit`.** They are the same size, but the 8B
  follows the image-rewrite accuracy rules the 4B ignores, and answered faster
  warm on an M5 Max. It is the `small` and `medium` tier in
  `scripts/model_tiers.json`, the compose, Makefile and `.env.example` default,
  and the `gutenkg imagine` rewrite default. Measured on a 24 GB M4 Pro beside
  FLUX; 16 GB is an estimate. `docs/INSTALLATION.md` has the measurements from
  both Macs.
- **The Apple container worker defaults to 4g, up from 2g.** At 2g the VM's
  page cache could not hold the hot part of the 5.9 GB index, so every query
  reread it from disk and searches took 3-8 s. With room for the cache, warm
  searches take 0.5-0.7 s, the same as Docker, while the worker VM costs the
  Mac about 3 GB against Docker Desktop's 12 GB. `docs/APPLE_CONTAINERS.md`
  records the measurements. Docker stays the default runtime.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
