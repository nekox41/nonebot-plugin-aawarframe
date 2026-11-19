"""Packaging and release workflow contract tests."""

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_single_package_layout():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["name"] == "nonebot-plugin-aawarframe"
    assert (ROOT / "nonebot_plugin_aawarframe" / "__init__.py").is_file()
    assert not (ROOT / "core").exists()
    assert not (ROOT / "core" / "nonebot_plugin_aawfcore").exists()


def test_protocol_adapters_remain_optional():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    dependencies = project["dependencies"]
    assert not any("nonebot-adapter-onebot" in item for item in dependencies)
    assert not any("nonebot-adapter-qq" in item for item in dependencies)
    assert "qq" in project["optional-dependencies"]
    assert "onebot" in project["optional-dependencies"]


def test_release_publishes_pypi_and_manual_plugin_archive():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "branches: [master]" in workflow
    assert "id-token: write" in workflow
    assert "name: aawarframe" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "softprops/action-gh-release@v2" in workflow
    assert "nonebot_plugin_aawarframe-v" in workflow
    assert "publish-core:" not in workflow
    assert "publish-qq:" not in workflow
    assert "publish-onebot:" not in workflow
