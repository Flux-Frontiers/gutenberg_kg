"""The iOS/macOS apps carry the package's version.

The apps sat at ``1.0`` while the package reached 1.22.2, because their version
lived in three hand-edited places nothing checked. They now track
``pyproject.toml``; this fails as soon as any of the copies differs, so a
release that bumps the package without the apps does not pass CI.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _package_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


@pytest.mark.parametrize("project", ["app/ios/project.yml", "app/macos/project.yml"])
def test_project_marketing_version_matches_the_package(project):
    text = (ROOT / project).read_text()
    versions = re.findall(r'MARKETING_VERSION:\s*"([^"]+)"', text)
    assert versions == [_package_version()], f"{project}: {versions}"


@pytest.mark.parametrize("project", ["app/ios/project.yml", "app/macos/project.yml"])
def test_info_plist_reads_the_build_settings(project):
    # A literal here is what froze the apps at 1.0: the build setting moved,
    # the Info.plist did not.
    text = (ROOT / project).read_text()
    assert 'CFBundleShortVersionString: "$(MARKETING_VERSION)"' in text
    assert 'CFBundleVersion: "$(CURRENT_PROJECT_VERSION)"' in text


def test_swift_fallback_matches_the_package():
    swift = ROOT / "app/GutenbergKGKit/Sources/KnowledgePressUI/AppVersion.swift"
    match = re.search(r'static let fallback = "([^"]+)"', swift.read_text())
    assert match and match.group(1) == _package_version()


@pytest.mark.parametrize("manifest", ["package.json", "package-lock.json"])
def test_web_forest_version_matches_the_package(manifest):
    # The web forest sat at 0.1.0 the same way the apps sat at 1.0.
    data = json.loads((ROOT / "web/knowledge-press-forest" / manifest).read_text())
    assert data["version"] == _package_version(), f"{manifest}: {data['version']}"
    if manifest == "package-lock.json":
        assert data["packages"][""]["version"] == _package_version()
