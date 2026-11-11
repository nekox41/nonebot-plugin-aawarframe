# 作用：实现 models 层的 wiki 功能。
# 编写日期：2026-11-07
# 作者：Aameow

from pydantic import BaseModel, Field, HttpUrl, RootModel, StrictStr, field_validator


class WikiEntry(BaseModel):
    title: str = Field(min_length=1)
    description: str
    url: HttpUrl

    @field_validator("url")
    @classmethod
    def require_wiki_link(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https" or value.host != "warframe.huijiwiki.com":
            raise ValueError("Wiki 返回了非本站 HTTPS 链接")
        return value


class WikiSearchResult(BaseModel):
    query: str
    entries: list[WikiEntry] = Field(max_length=10)


class OpenSearchResponse(
    RootModel[tuple[StrictStr, list[StrictStr], list[StrictStr], list[StrictStr]]]
):
    def to_result(self) -> WikiSearchResult:
        query, titles, descriptions, urls = self.root
        if not len(titles) == len(descriptions) == len(urls):
            raise ValueError("Wiki 搜索结果各字段数量不一致")
        return WikiSearchResult(
            query=query,
            entries=[
                WikiEntry(title=title, description=description, url=url)
                for title, description, url in zip(titles, descriptions, urls, strict=True)
            ],
        )
