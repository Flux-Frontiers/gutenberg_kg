# Release Notes -- v1.34.0

> Released: 2026-11-07

### Added

- **Anthropic as a synthesis provider.** The chat UI's Provider dropdown lists
  Anthropic, and the worker answers with Claude when a request names
  `backend: "anthropic"` (kgmodule-utils 0.30.0). `docker-compose.yml`,
  `make run` and `docker/.env.example` pass `ANTHROPIC_API_KEY` to the worker
  beside `OPENAI_API_KEY`.

### Changed

- **kgmodule-utils floor 0.30.0** (pyproject, Dockerfile
  `KGMODULE_UTILS_VERSION`, runpod). It also makes OpenAI's gpt-5 and later
  models answer: 0.29.2 sent parameters they reject, and only the GPT-4
  family worked. The model list for OpenAI now holds only chat models.
- **The published worker image names its release.** `make publish-worker-image`
  stamps the OCI version and revision labels, so `docker buildx imagetools
  inspect` shows which release and commit an image was built from.

### Fixed

- **Live moots work from the Knowledge Press app by default.** The default
  `GUTENKG_CORS_ORIGINS` in `docker-compose.yml` and `make run` now includes
  `kp-forest://forest`, the origin of the app's Forest tab. Without it, the
  preflight got a 405 until someone edited `docker/.env`.
- **A moot's model failure says what is wrong.** The error told every case to
  check the endpoint. It now separates an endpoint that cannot list its models,
  a model the endpoint does not serve, and a served model that returned nothing.
  This matters on oMLX, where moots ask for `Qwen3.8-27B-4bit` rather than
  `VLLM_MODEL`.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
