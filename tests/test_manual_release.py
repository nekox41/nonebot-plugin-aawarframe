import zipfile

from scripts import package_release


def test_manual_qq_bundle_installs_core_as_a_python_distribution(tmp_path):
    (tmp_path / "dist/core").mkdir(parents=True)
    (tmp_path / "dist/qq").mkdir(parents=True)
    (tmp_path / "dist/core/nonebot_plugin_aawfcore-0.23.2-py3-none-any.whl").write_bytes(b"core")
    (tmp_path / "dist/qq/nonebot_plugin_aawfqq-0.23.2-py3-none-any.whl").write_bytes(b"qq")

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
    (tmp_path / "dist/core").mkdir(parents=True)
    (tmp_path / "dist/core/nonebot_plugin_aawfcore-0.23.2-py3-none-any.whl").write_bytes(b"core")

    package_release.build("0.23.2", root=tmp_path)

    archive_path = tmp_path / "dist/manual/nonebot-plugin-aawfcore-manual-v0.23.2.zip"
    with zipfile.ZipFile(archive_path) as archive:
        wheels = [name for name in archive.namelist() if name.endswith(".whl")]
        assert wheels == ["wheels/nonebot_plugin_aawfcore-0.23.2-py3-none-any.whl"]
