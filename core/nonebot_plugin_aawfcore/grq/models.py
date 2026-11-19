# 作用：定义 GRQ 域策略、统一资源和结构化搜索结果。
# 编写日期：2026-11-13
# 作者：Aameow

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Domain(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")
    title: str = Field(min_length=1, max_length=100)
    description: str = ""
    searchable: bool = True
    fuzzy: bool = True
    aliases: bool = True
    semantic_guard: bool = False
    mode: str = Field(default="resource", pattern=r"^(resource|text|document)$")


class Resource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(min_length=1, max_length=2000)
    identifiers: dict[str, str] = Field(default_factory=dict)
    names: dict[str, str] = Field(default_factory=dict)
    texts: dict[str, str] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list, max_length=1000)
    metadata: dict = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("names", "texts", "identifiers")
    @classmethod
    def validate_values(cls, values):
        if any(not key or not value or len(value) > 20000 for key, value in values.items()):
            raise ValueError("名称、文本和标识不能为空，单项最长 20000 字")
        return values

    @field_validator("aliases")
    @classmethod
    def validate_aliases(cls, values):
        if any(not value.strip() or len(value) > 120 for value in values):
            raise ValueError("别名长度应为 1–120 字")
        return list(dict.fromkeys(values))

    def name(self, lang="zh-hans"):
        return self.names.get(lang) or self.texts.get(lang) or self.names.get("en") or self.id


class SearchResult(BaseModel):
    status: str
    candidates: list[Resource] = Field(default_factory=list)
    exact: bool = False
    scores: list[float] = Field(default_factory=list)

    @property
    def resource(self):
        return self.candidates[0] if self.status == "found" else None
