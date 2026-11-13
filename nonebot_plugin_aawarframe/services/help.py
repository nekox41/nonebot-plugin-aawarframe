# 作用：按页展示命令、别名和使用示例。
# 编写日期：2026-11-11
# 作者：Aameow

from ..models.common import Card, Section
from ..models.errors import UserInputError

HELP_PAGES = [
    [
        (
            "帮助与状态",
            [
                ["help (wf帮助)\nwf help", "查看帮助；help 2 查看第二页"],
                ["平原", "查看各大平原和地球的环境状态"],
                [
                    "裂缝 (裂隙)\n钢铁裂缝 (钢铁裂隙)\n九重天 (九重天裂缝)",
                    "普通、钢铁之路与九重天裂缝",
                ],
                [
                    "时光科研 (时光)\n深层科研 (深层)",
                    "本周三场任务、偏差、普通与精英风险及个人变量",
                ],
                ["午夜电波 (电波)", "当前每日、每周和精英每周任务、声望与剩余时间"],
            ],
        ),
        (
            "赏金",
            [
                ["赏金", "地球三个帐篷；圣所、扎里曼第 4、5 项；1999 第 4、5 项与杀毒"],
                [
                    "地球赏金 (地球)\n金星赏金 (金星)\n火卫二赏金 (火卫二)",
                    "本期赏金与据点任务；追加编号查看奖励，例如：地球 1",
                ],
                [
                    "圣所赏金\n扎里曼赏金\n1999赏金",
                    "任务和额外目标；追加编号查看奖励，例如：圣所赏金 1",
                ],
            ],
        ),
    ],
    [
        (
            "每周任务与奖励",
            [
                ["氏族 (氏族奖励)", "本周与下周奖励、积分门槛和双倍区域"],
                ["日历", "1999 本周日历任务与可选奖励"],
                ["钢精", "本周与下周钢铁精华兑换物品及价格"],
                ["回廊", "本周与下周普通战甲、钢铁回廊灵化选项"],
                ["灵化", "完整灵化武器周轮换表，高亮本周"],
            ],
        ),
    ],
    [
        (
            "紫卡与市场",
            [
                ["紫卡排行\n已洗紫卡排行", "未洗／已洗周排行；每页 10 条，热度 ≥ 5"],
                ["紫卡排行 2\n已洗紫卡排行 2", "按中位价排序，查看第 2 页"],
                ["紫卡排行 3 热度\n已洗紫卡排行 3 热度", "按热度排序，查看第 3 页"],
                ["紫卡统计 伯斯顿", "按中文或英文武器名称查询周统计"],
                ["wk 关键词 / wiki 关键词", "最多返回 3 条维基标题、摘要和链接"],
                ["wm 物品名\nwm 满级物品名", "在线买卖挂单；物品名允许空格"],
                ["wm 物品名 --rank 0 --subtype blueprint", "按物品支持情况筛选等级或子类型"],
            ],
        ),
        (
            "暂不可用",
            [
                ["仲裁\n今日仲裁\n高效仲裁", "官方数据支撑尚未验证"],
            ],
        ),
    ],
]


def help_card(arguments: str = "") -> Card:
    value = arguments.strip() or "1"
    if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= len(HELP_PAGES):
        raise UserInputError(
            f"帮助共 {len(HELP_PAGES)} 页，请输入 1～{len(HELP_PAGES)} 的页码，例如 help 2。"
        )
    page = int(value)
    return Card(
        title="Warframe 助手 · 命令帮助",
        source="本地命令说明",
        help_mode=True,
        page_number=page,
        total_pages=len(HELP_PAGES),
        sections=[
            Section(title=title, columns=["命令 (别名)", "说明"], rows=rows)
            for title, rows in HELP_PAGES[page - 1]
        ],
        notes=[
            f"第 {page} / {len(HELP_PAGES)} 页 · 发送 "
            + "、".join(f"help {i}" for i in range(1, len(HELP_PAGES) + 1))
            + " 换页。",
            "蓝色为命令，括号内为等效别名；同类命令分行展示。",
        ],
    )
