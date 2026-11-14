# Desc: 保存管理配置并执行即时生效的命令路由和黑白名单规则。
# Date: 2026-11-14
# Author: Aameow

import asyncio
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..grq import GameResourceQuery


class ACL(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allow_users: list[str] = Field(default_factory=list, max_length=10000)
    allow_groups: list[str] = Field(default_factory=list, max_length=10000)
    deny_users: list[str] = Field(default_factory=list, max_length=10000)
    deny_groups: list[str] = Field(default_factory=list, max_length=10000)

    @model_validator(mode="after")
    def validate_ids(self):
        for values in (self.allow_users, self.allow_groups, self.deny_users, self.deny_groups):
            if any(not v.isdecimal() or len(v) > 20 for v in values):
                raise ValueError("QQ 号和群号必须是数字")
        return self

    def permits(self, user: str, group: str | None):
        if user in self.deny_users or (group and group in self.deny_groups):
            return False
        return not (self.allow_users or self.allow_groups) or (
            user in self.allow_users or bool(group and group in self.allow_groups)
        )


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feature: str
    name: str = Field(min_length=1, max_length=40)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    enabled: bool = True
    prefix: Literal["nonebot", "none", "optional"] = "nonebot"
    acl: ACL = Field(default_factory=ACL)

    @model_validator(mode="after")
    def validate_names(self):
        for name in [self.name, *self.aliases]:
            if not name or len(name) > 40 or any(c.isspace() or ord(c) < 32 for c in name):
                raise ValueError("命令和别名不能包含空白，最长 40 字")
        return self


class Options(BaseModel):
    model_config = ConfigDict(extra="forbid")
    http_timeout: float = Field(default=12, gt=0, le=60)
    worldstate_ttl: float = Field(default=45, gt=0, le=180)
    market_ttl: float = Field(default=30, gt=0, le=90)
    wiki_ttl: float = Field(default=300, ge=0, le=3600)
    wiki_interval: float = Field(default=1, ge=1, le=60)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    acl: ACL = Field(default_factory=ACL)
    options: Options = Field(default_factory=Options)
    commands: list[Command]

    @model_validator(mode="after")
    def unique_names(self):
        features, names = set(), {}
        for cmd in self.commands:
            if cmd.feature in features:
                raise ValueError("功能不能重复")
            features.add(cmd.feature)
            for name in [cmd.name, *cmd.aliases]:
                if name in names and names[name] != cmd.feature:
                    raise ValueError("命令冲突：" + name)
                names[name] = cmd.feature
        if features != {f for _, _, f in DEFAULT_COMMANDS}:
            raise ValueError("不能添加或删除功能，请使用启用开关")
        return self


DEFAULT_COMMANDS = [
    ("平原", set(), "plains"),
    ("突击", set(), "sortie"),
    ("奸商", set(), "void_trader"),
    ("入侵", set(), "invasions"),
    ("执刑官", set(), "archon"),
    ("时光科研", {"时光"}, "temporal"),
    ("深层科研", {"深层"}, "deep"),
    ("裂缝", {"裂隙"}, "fissures"),
    ("钢铁裂缝", {"钢铁裂隙"}, "steel_fissures"),
    ("九重天", {"九重天裂缝"}, "railjack_fissures"),
    ("氏族", {"氏族奖励"}, "clan"),
    ("午夜电波", {"电波"}, "nightwave"),
    ("日历", set(), "calendar"),
    ("钢精", set(), "steel_path"),
    ("回廊", set(), "circuit"),
    ("灵化", set(), "incarnons"),
    ("赏金", set(), "bounty_summary"),
    ("地球赏金", {"地球"}, "bounties"),
    ("金星赏金", {"金星"}, "venus_bounties"),
    ("火卫二赏金", {"火卫二"}, "deimos_bounties"),
    ("圣所赏金", set(), "sanctum_bounties"),
    ("扎里曼赏金", set(), "zariman_bounties"),
    ("1999赏金", set(), "hex_bounties"),
    ("仲裁", set(), "arbitration"),
    ("今日仲裁", set(), "today_arbitration"),
    ("高效仲裁", set(), "efficient_arbitration"),
    ("wm", set(), "market"),
    ("wk", {"wiki"}, "wiki"),
    ("紫卡排行", set(), "riven_ranking"),
    ("已洗紫卡排行", set(), "rolled_riven_ranking"),
    ("紫卡统计", set(), "riven_statistics"),
    ("紫卡数值", set(), "riven_values"),
]


class Control:
    def __init__(self, registry: GameResourceQuery, options=None):
        self.registry = registry
        default = Settings(
            commands=[Command(feature=f, name=n, aliases=sorted(a)) for n, a, f in DEFAULT_COMMANDS]
        )
        if options:
            default.options = Options(**options)
        raw, self.revision = registry.read_setting("control", default.model_dump())
        features = {cmd.feature for cmd in default.commands}
        raw["commands"] = [item for item in raw["commands"] if item["feature"] in features]
        known = {item["feature"] for item in raw["commands"]}
        raw["commands"].extend(cmd.model_dump() for cmd in default.commands if cmd.feature not in known)
        self.settings = Settings.model_validate(raw)
        self.apply = None
        self._compile()

    def _compile(self):
        self.routes = tuple(
            sorted(
                (
                    (name, cmd)
                    for cmd in self.settings.commands
                    for name in {cmd.name, *cmd.aliases}
                ),
                key=lambda pair: (-len(pair[0]), pair[0]),
            )
        )

    def update(self, raw, revision):
        settings = Settings.model_validate(raw)
        self.revision = self.registry.write_setting("control", settings.model_dump(), revision)
        self.settings = settings
        self._compile()
        if self.apply:
            self.apply(settings.options)
        return self.revision

    async def update_async(self, raw, revision):
        settings = Settings.model_validate(raw)
        self.revision = await asyncio.to_thread(
            self.registry.write_setting, "control", settings.model_dump(), revision
        )
        self.settings = settings
        self._compile()
        if self.apply:
            self.apply(settings.options)
        return self.revision

    def route(self, text, starts, user, group=None):
        # 先识别最长命令，再判断开关和名单；被停用的长命令不会误触发短命令。
        matches = []
        for name, command in self.routes:
            prefixes = starts if command.prefix == "nonebot" else {""}
            if command.prefix == "optional":
                prefixes = {*starts, ""}
            for prefix in prefixes:
                token = prefix + name
                if text.startswith(token):
                    matches.append((len(token), command, text[len(token) :].strip()))
        if not matches:
            return None
        _, command, args = max(matches, key=lambda m: m[0])
        if (
            not command.enabled
            or not self.settings.acl.permits(user, group)
            or not command.acl.permits(user, group)
        ):
            return None
        return command.feature, args
