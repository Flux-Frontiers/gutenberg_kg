# Release Notes -- v1.22.1

> Released: 2026-09-18

Casting the forest to the Looking Glass now sweeps a 35-degree view cone instead of the panel's full cone.

## What changed

**Cast to Looking Glass fuses cleanly.** The `kgmodule-utils` floor moves to 0.22.0, which routes the Cast button through `quiltwright.quilt.resolve_view_cone`. The 16" landscape preset's native cone is 50 degrees -- wider than reliably fuses -- so casts previously showed ghosting the CLI's own renders never had. No code in this repo changed; the fix arrives through the shared `cast_scene_to_looking_glass` helper. The `quiltwright` pin moves to 0.14.1 alongside it in both the `viz3d` and `pov` extras, which the extras already required transitively.

The floor is also synced in `docker/Dockerfile` and `runpod/requirements.txt`, which `check_pins` verifies on every build.

## Upgrading

`poetry update kgmodule-utils quiltwright` (or `pip install -U kgmodule-utils quiltwright`). No config or API changes.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
