"""Single wheel replaces the old three-wheel manual archive layout."""
from pathlib import Path
import tomllib

def test_one_pypi_project():
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["name"] == "nonebot-plugin-aawarframe"
    assert "nonebot-plugin-aawfcore" not in project["dependencies"]
    assert "nonebot-adapter-onebot" not in project["dependencies"]
    assert "nonebot-adapter-qq" not in project["dependencies"]
    assert "qq" in project["optional-dependencies"]
    assert "onebot" in project["optional-dependencies"]

def test_release_uses_pypi_oidc():
    text = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "id-token: write" in text
    assert "name: aawarframe" in text
    assert "pypa/gh-action-pypi-publish@release/v1" in text
    assert "publish-core:" not in text
    assert "publish-qq:" not in text
    assert "publish-onebot:" not in text
