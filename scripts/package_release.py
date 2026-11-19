"""Bundle the independently built wheels for manual NoneBot2 installation."""

import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTIONS = {
    "core": ("nonebot-plugin-aawfcore", "core"),
    "qq": ("nonebot-plugin-aawfqq", "qq"),
    "onebot": ("nonebot-plugin-aawfonebot", "onebot"),
}
BUNDLES = {
    "core": ("core",),
    "qq": ("core", "qq"),
    "onebot": ("core", "onebot"),
}
PLUGIN_CONFIG = {
    "core": ("nonebot_plugin_aawfcore", None),
    "qq": ("nonebot_plugin_aawfqq", "nonebot.adapters.qq"),
    "onebot": ("nonebot_plugin_aawfonebot", "nonebot.adapters.onebot.v11"),
}


def find_wheel(root: Path, package: str, version: str) -> Path:
    distribution, directory = DISTRIBUTIONS[package]
    prefix = distribution.replace("-", "_").lower() + f"-{version}-"
    matches = [
        path for path in (root / "dist" / directory).glob("*.whl")
        if path.name.lower().startswith(prefix)
    ]
    if len(matches) != 1:
        raise SystemExit(
            f"预期在 dist/{directory} 找到一个 {distribution} {version} wheel，实际找到 {len(matches)} 个"
        )
    return matches[0]


def build(version: str, root: Path = ROOT) -> None:
    root = Path(root)
    output = root / "dist" / "manual"
    output.mkdir(parents=True, exist_ok=True)

    for bundle, packages in BUNDLES.items():
        wheels = [find_wheel(root, package, version) for package in packages]
        plugin, adapter = PLUGIN_CONFIG[bundle]
        install = " ".join(f"./wheels/{wheel.name}" for wheel in wheels)
        adapter_config = f'adapters = ["{adapter}"]' if adapter else "# No protocol adapter is required by the Core-only bundle."
        docs = (
            "AAWarframe manual wheel installation\n"
            f"Version: {version}; bundle: {bundle}\n\n"
            "Requirements: Python 3.12 and an existing NoneBot2 project.\n\n"
            "1. Extract this archive anywhere outside src/plugins.\n"
            "2. Activate the NoneBot project's virtual environment.\n"
            f"3. Install the included distributions:\n   python -m pip install {install}\n"
            "4. Merge the following settings into the project's pyproject.toml "
            "[tool.nonebot] section:\n\n"
            "[tool.nonebot]\n"
            f'plugins = ["{plugin}"]\n'
            f"{adapter_config}\n\n"
            "Do not copy the installed Core package into src/plugins. The protocol "
            "package imports the Core as the normal Python distribution installed above.\n"
            "Persistent data and generated game resources are stored under "
            "data/aawarframe by default.\n"
            "The included wheels declare and install their Python dependencies.\n"
        )
        path = output / f"nonebot-plugin-aawf{bundle}-manual-v{version}.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=5) as archive:
            for wheel in wheels:
                archive.write(wheel, arcname=f"wheels/{wheel.name}")
            archive.writestr("INSTALL.txt", docs)
        print(path, path.stat().st_size)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    build(args.version)
