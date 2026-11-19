import json

from nonebot_plugin_aawfcore.localization.resources import configure_resources
from nonebot_plugin_aawfcore.services import riven_values


def test_riven_rules_are_loaded_from_immutable_package_assets(tmp_path, monkeypatch):
    packaged = tmp_path / "package-assets"
    runtime_cache = tmp_path / "runtime-cache"
    packaged.mkdir()
    runtime_cache.mkdir()
    (packaged / "riven_stats.json").write_text(
        json.dumps({"source": "packaged", "attributes": [], "layouts": {}, "disposition": 1.2}),
        encoding="utf-8",
    )
    (runtime_cache / "riven_stats.json").write_text(
        json.dumps({"source": "runtime-cache"}), encoding="utf-8"
    )

    monkeypatch.setattr(riven_values, "PACKAGED", packaged)
    configure_resources(runtime_cache)

    assert riven_values.RivenValuesService().rules["source"] == "packaged"
