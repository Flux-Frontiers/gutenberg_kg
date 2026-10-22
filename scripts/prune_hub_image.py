#!/usr/bin/env python3
# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""
Delete the image a push to Docker Hub just replaced.

``make publish-worker-image`` pushes a new image under the same tag
(``latest``). Docker Hub keeps the replaced one, untagged, with its own copy of
the multi-GB corpus layers; nothing ever pulls it again, and each publish added
about 6 GB to the repository until someone deleted them by hand.

Docker Hub's registry API can delete a manifest by digest once nothing
references it, but it cannot list untagged images
(https://docs.docker.com/reference/api/registry/latest/). So the publish target
records the tag's digest before it pushes and hands it here afterwards. This
deletes that image index, then the per-platform and attestation manifests it
listed. A manifest still referenced (the new image shares it, or another tag
points at it) is refused by the registry with 403 and left alone.

Needs a Docker Hub personal access token with Read, Write and Delete:
``DOCKERHUB_USERNAME`` and ``DOCKERHUB_TOKEN``. Without them it says what to
set and exits 0, so a publish never fails for want of cleanup.

Usage:
    OLD=$(python3 scripts/prune_hub_image.py digest docker.io/egsuchanek/corpus-gutenberg:latest)
    ... push ...
    python3 scripts/prune_hub_image.py prune docker.io/egsuchanek/corpus-gutenberg:latest "$OLD"
    python3 scripts/prune_hub_image.py prune ... --dry-run

``digest`` needs no token for a public repository. An image on any registry
other than Docker Hub is left alone.

Exit status:
    0  pruned, nothing to prune, or skipped for want of a token
    1  a request failed
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request

AUTH_URL = "https://auth.docker.io/token"
REGISTRY = "https://registry-1.docker.io"
INDEX_TYPES = ", ".join(
    [
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]
)


def parse_image(image: str) -> tuple[str, str] | None:
    """Split ``[docker.io/]namespace/repo[:tag]`` into the repository name and tag.

    :param image: The image reference the Makefile pushes.
    :returns: ``("namespace/repo", "tag")``, the tag ``latest`` by default; or
        ``None`` for an image on another registry, which this leaves alone.
    """
    name = image.removeprefix("docker.io/")
    repo, _, tag = name.partition(":")
    if repo.count("/") != 1 or "." in repo.split("/")[0]:
        return None
    return repo, tag or "latest"


def child_digests(index: dict) -> list[str]:
    """The manifests an image index lists: each platform and each attestation.

    :param index: The parsed index; a single-platform manifest has none.
    """
    return [m["digest"] for m in index.get("manifests", [])]


def plan(old: str, current: str, index: dict) -> list[str]:
    """The digests to delete, the index first so its children are unreferenced.

    :param old: The digest the tag pointed to before the push.
    :param current: The digest it points to now.
    :param index: The old image's manifest, as the registry returns it.
    :returns: Nothing when the push did not move the tag.
    """
    if not old or old == current:
        return []
    return [old, *[d for d in child_digests(index) if d != current]]


def _request(
    url: str, *, token: str, method: str = "GET", accept: str = ""
) -> tuple[int, dict, bytes]:
    headers = {"Authorization": f"Bearer {token}"}
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            return res.status, dict(res.headers), res.read()
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers or {}), err.read()


def registry_token(repo: str, user: str = "", secret: str = "") -> str:
    """A bearer token: pull only when anonymous, pull, push and delete with a login."""
    actions = "pull,push,delete" if user else "pull"
    headers = {}
    if user:
        headers["Authorization"] = "Basic " + base64.b64encode(f"{user}:{secret}".encode()).decode()
    url = f"{AUTH_URL}?service=registry.docker.io&scope=repository:{repo}:{actions}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as res:
        return json.load(res)["token"]


def tag_digest(repo: str, tag: str, token: str) -> str:
    """The digest a tag points to, or ``""`` when the tag does not exist."""
    status, headers, _ = _request(
        f"{REGISTRY}/v2/{repo}/manifests/{tag}", token=token, method="HEAD", accept=INDEX_TYPES
    )
    digest = {k.lower(): v for k, v in headers.items()}.get("docker-content-digest", "")
    return digest if status == 200 else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("digest", help="print the digest a tag points to now (empty when none)")
    d.add_argument("image")
    p = sub.add_parser("prune", help="delete the image a push replaced")
    p.add_argument(
        "image", help="the image pushed, e.g. docker.io/egsuchanek/corpus-gutenberg:latest"
    )
    p.add_argument(
        "old", help="the tag's digest before the push, from `digest`; empty when there was none"
    )
    p.add_argument("--dry-run", action="store_true", help="list what would be deleted")
    args = parser.parse_args(argv)

    parsed = parse_image(args.image)
    if args.command == "digest":
        # Never fails a publish: no digest only means nothing gets pruned.
        try:
            print(tag_digest(*parsed, registry_token(parsed[0])) if parsed else "")
        except (urllib.error.URLError, OSError, KeyError, ValueError):
            print("")
        return 0

    if parsed is None:
        print(f"prune: {args.image} is not on Docker Hub; nothing deleted.")
        return 0
    if not args.old.startswith("sha256:"):
        print("prune: no earlier image under this tag; nothing to delete.")
        return 0
    user, secret = os.environ.get("DOCKERHUB_USERNAME", ""), os.environ.get("DOCKERHUB_TOKEN", "")
    if not (user and secret):
        print(
            f"prune: skipped. The replaced image {args.old[:19]} stays on Docker Hub, untagged.\n"
            "  Set DOCKERHUB_USERNAME and DOCKERHUB_TOKEN (a personal access token with\n"
            "  Read, Write and Delete) to delete it after each publish."
        )
        return 0

    repo, tag = parsed
    token = registry_token(repo, user, secret)
    current = tag_digest(repo, tag, token)
    if not current:
        print(f"prune: could not read {repo}:{tag}; nothing deleted.")
        return 1
    status, _, body = _request(
        f"{REGISTRY}/v2/{repo}/manifests/{args.old}", token=token, accept=INDEX_TYPES
    )
    if status == 404:
        print(f"prune: {args.old[:19]} is already gone.")
        return 0
    if status != 200:
        print(f"prune: could not read {args.old[:19]} (HTTP {status}); nothing deleted.")
        return 1
    digests = plan(args.old, current, json.loads(body))
    if not digests:
        print(f"prune: {repo}:{tag} still points at {args.old[:19]}; nothing to delete.")
        return 0
    failed = False
    for digest in digests:
        if args.dry_run:
            print(f"prune: would delete {repo}@{digest[:19]}")
            continue
        status, _, _ = _request(
            f"{REGISTRY}/v2/{repo}/manifests/{digest}", token=token, method="DELETE"
        )
        # 202 deleted; 500 is retried by Docker Hub in the background (its docs);
        # 403 means something still references it, so it is rightly kept.
        if status in (200, 202, 500):
            print(
                f"prune: deleted {repo}@{digest[:19]}"
                + (" (Hub finishes it in the background)" if status == 500 else "")
            )
        elif status in (403, 404):
            print(
                f"prune: kept {repo}@{digest[:19]} (HTTP {status}: still referenced or already gone)"
            )
        else:
            print(f"prune: failed on {repo}@{digest[:19]} (HTTP {status})")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
