"""只安装 QQ 官方适配器的最小 NoneBot2 启动示例。"""

import nonebot
from nonebot.adapters.qq import Adapter as QQAdapter


def main() -> None:
    nonebot.init()
    driver = nonebot.get_driver()
    driver.register_adapter(QQAdapter)
    nonebot.load_plugin("nonebot_plugin_aawarframe")
    nonebot.run()


if __name__ == "__main__":
    main()
