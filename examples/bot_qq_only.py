"""只安装 nonebot-adapter-qq 的最小 QQ 官方机器人启动示例。

与用户项目中的 bot.py 不同，这份示例完全不导入 OneBot。
请在用户项目中配置好 .env.prod 的 QQ_BOTS、DRIVER 和 RENDER 等参数。
"""

import nonebot
from nonebot.adapters.qq import Adapter as QQAdapter


def main() -> None:
    nonebot.init()
    driver = nonebot.get_driver()
    driver.register_adapter(QQAdapter)
    nonebot.load_plugin("nonebot_plugin_aawfqq")
    nonebot.run()


if __name__ == "__main__":
    main()
