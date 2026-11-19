import zipfile

from scripts import package_release


def create_test_wheels(root):
    core_dir = root / "dist/core"
    qq_dir = root / "dist/qq"
    onebot_dir = root / "dist/onebot"
    core_dir.mkdir(parents=True)
    qq_dir.mkdir(parents=True)
    onebot_dir.mkdir(parents=True)

    core_wheel = core_dir / "nonebot_plugin_aawfcore-0.23.2-py3-none-any.whl"
    with zipfile.ZipFile(core_wheel, "w") as wheel:
        wheel.writestr("nonebot_plugin_aawfcore/assets/offline.tar.gz", b"offline")
        wheel.writestr("nonebot_plugin_aawfcore/assets/riven_stats.json", b"{}")
    (qq_dir / "nonebot_plugin_aawfqq-0.23.2-py3-none-any.whl").write_bytes(b"qq")
    (onebot_dir / "nonebot_plugin_aawfonebot-0.23.2-py3-none-any.whl").write_bytes(b"onebot")


def test_manual_qq_bundle_installs_core_as_a_python_distribution(tmp_path):
    create_test_wheels(tmp_path)

    package_release.build("0.23.2", root=tmp_path)

    archive_path = tmp_path / "dist/manual/nonebot-plugin-aawfqq-manual-v0.23.2.zip"
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "wheels/nonebot_plugin_aawfcore-0.23.2-py3-none-any.whl" in names
        assert "wheels/nonebot_plugin_aawfqq-0.23.2-py3-none-any.whl" in names
        assert not any(name.startswith("src/plugins/") for name in names)
        instructions = archive.read("INSTALL.txt").decode()
        assert 'plugins = ["nonebot_plugin_aawfqq"]' in instructions
        assert 'adapters = ["nonebot.adapters.qq"]' in instructions
        assert "Do not copy the installed Core package into src/plugins." in instructions


def test_manual_core_bundle_contains_only_core_wheel(tmp_path):
    create_test_wheels(tmp_path)

    package_release.build("0.23.2", root=tmp_path)

    archive_path = tmp_path / "dist/manual/nonebot-plugin-aawfcore-manual-v0.23.2.zip"
    with zipfile.ZipFile(archive_path) as archive:
        wheels = [name for name in archive.namelist() if name.endswith(".whl")]
        assert wheels == ["wheels/nonebot_plugin_aawfcore-0.23.2-py3-none-any.whl"]
