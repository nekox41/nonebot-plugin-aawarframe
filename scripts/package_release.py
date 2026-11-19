"""为手动 src/plugins 安装创建三份独立可解压 GitHub Release 包。"""

import argparse
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "manual"
CORE = ROOT / "core" / "nonebot_plugin_aawfcore"
PLUGINS = {
    "core": None,
    "qq": ROOT / "nonebot_plugin_aawfqq" / "nonebot_plugin_aawfqq",
    "onebot": ROOT / "nonebot_plugin_aawfonebot" / "nonebot_plugin_aawfonebot",
}
EXTRAS = {
    "core": [],
    "qq": ["nonebot-adapter-qq>=1.7.4,<2"],
    "onebot": ["nonebot-adapter-onebot>=2.4.6,<3"],
}


def build(version: str) -> None:
    with (ROOT / "core" / "pyproject.toml").open("rb") as inp:
        requirements = tomllib.load(inp)["project"]["dependencies"]
    archive_file = CORE / "assets" / "offline.tar.gz"
    if not archive_file.exists():
        raise SystemExit("先运行 python scripts/build_resources.py 生成资源")
    DIST.mkdir(parents=True, exist_ok=True)
    for name, frontend in PLUGINS.items():
        path = DIST / f"nonebot-plugin-aawf{name}-manual-v{version}.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=5) as archive:
            for folder in (CORE, frontend):
                if folder is None:
                    continue
                for file in folder.rglob("*"):
                    if not file.is_file() or file.suffix == ".pyc" or "__pycache__" in file.parts:
                        continue
                    package_relative = file.relative_to(folder.parent)
                    zip_name = "src/plugins/" + str(package_relative)
                    archive.write(file, arcname=zip_name)
            req = "\n".join([*requirements, *EXTRAS[name]]) + "\n"
            archive.writestr("AAWF-REQUIREMENTS.txt", req)
            docs = (
                "AAWarframe manual NoneBot2 installation\n"
                f"Version: {version}; protocol: {name}\n"
                "1. unzip <archive>.zip -d <NoneBot2 project>/\n"
                "2. python -m pip install -r AAWF-REQUIREMENTS.txt\n"
                "3. In pyproject.toml [tool.nonebot] set plugin_dirs = ['src/plugins'];\n"
                f"   keep only nonebot_plugin_aawf{name} as the frontend plugin.\n"
                "4. Register the selected NoneBot adapter in your bot.py.\n"
                "The core uses data/aawarframe as the persistent shared data folder.\n"
            )
            archive.writestr("INSTALL.txt", docs)
        print(path, path.stat().st_size)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    build(args.version)
