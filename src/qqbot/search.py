"""联网搜索：DeepSeek 官方 Search / Fetch API。

复用 DEEPSEEK_API_KEY，不需要额外账号。httpx 配置与 ChatClient 保持一致
（跟随系统代理），因为这个接口和对话走同一条网络路径。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

log = logging.getLogger(__name__)

SEARCH_PATH = "/v1/tools/search"
FETCH_PATH = "/v1/tools/fetch"


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    summary: str = ""
    site: str = ""
    published: str = ""
    authority: int = -1
    score: float = 0.0


class SearchError(Exception):
    """带用户可读文案的搜索失败，handler 直接把它转成字符串回给模型。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class SearchProvider(Protocol):
    name: str
    available: bool

    async def search(self, query: str, count: int) -> list[SearchResult]: ...

    async def fetch(self, url: str) -> tuple[str, str]: ...

    async def close(self) -> None: ...


class NullSearch:
    """没配 key 或关了搜索时用，工具层据此不注册。"""

    name = "none"
    available = False

    async def search(self, query: str, count: int) -> list[SearchResult]:
        return []

    async def fetch(self, url: str) -> tuple[str, str]:
        return "", ""

    async def close(self) -> None:
        return None


class DeepSeekSearch:
    name = "deepseek"
    available = True

    def __init__(self, settings) -> None:
        self.base = settings.deepseek_base_url.rstrip("/")
        self.key = settings.deepseek_api_key
        self.timeout = settings.search_timeout
        self._client = httpx.AsyncClient(timeout=self.timeout)

    async def search(self, query: str, count: int) -> list[SearchResult]:
        data = await self._post(
            SEARCH_PATH,
            {"query": query, "count": count, "need_content": False},
        )
        items = data.get("results")
        if not isinstance(items, list):
            return []
        return [
            self._to_result(item) for item in items if isinstance(item, dict)
        ]

    async def fetch(self, url: str) -> tuple[str, str]:
        data = await self._post(FETCH_PATH, {"url": url}, missing="这个页面打不开")
        title = str(data.get("title") or "").strip()
        content = str(data.get("content") or "").strip()
        return title, content

    @staticmethod
    def _to_result(item: dict) -> SearchResult:
        raw_authority = item.get("authority")
        try:
            authority = int(raw_authority)
        except (TypeError, ValueError):
            authority = -1
        raw_score = item.get("rerank_score")
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            score = 0.0
        return SearchResult(
            title=str(item.get("title") or "").strip(),
            url=str(item.get("url") or "").strip(),
            snippet=str(item.get("snippet") or "").strip(),
            summary=str(item.get("summary") or "").strip(),
            site=str(item.get("site_name") or "").strip(),
            published=str(item.get("date") or "").strip(),
            authority=authority,
            score=score,
        )

    async def _post(
        self, path: str, payload: dict, missing: str = "搜索暂时用不了"
    ) -> dict:
        if not self.key:
            raise SearchError("搜索没配好，先设置 DEEPSEEK_API_KEY")

        url = f"{self.base}{path}"
        headers = {"Authorization": f"Bearer {self.key}"}
        last_error = ""

        # 文档要求：408/429/5xx 可以重试，其他 4xx 改了请求再试
        for _attempt in range(2):
            try:
                resp = await self._client.post(url, json=payload, headers=headers)
            except httpx.TimeoutException:
                last_error = "timeout"
                continue
            except Exception as exc:  # noqa: BLE001
                log.warning("搜索请求失败（%s）：%s", path, exc)
                raise SearchError("搜索暂时用不了") from exc

            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError as exc:
                    raise SearchError("搜索结果看不懂，解析失败") from exc
                return data if isinstance(data, dict) else {}

            if resp.status_code == 402:
                raise SearchError("搜索账户余额不足，去 DeepSeek 平台充值")
            if resp.status_code == 429:
                raise SearchError("搜索请求太频繁，歇一下")
            if resp.status_code == 404:
                raise SearchError(missing)
            if resp.status_code == 408 or resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
                continue
            log.warning(
                "搜索接口返回 %s：%s", resp.status_code, resp.text[:200]
            )
            raise SearchError("搜索暂时用不了")

        log.warning("搜索重试后仍失败（%s %s）", path, last_error)
        raise SearchError("搜索暂时用不了")

    async def close(self) -> None:
        await self._client.aclose()


def build_search(settings):
    """按配置挑 provider；不可用时返回 NullSearch，工具层据此不注册。"""
    if not settings.search_enabled:
        log.info("联网搜索未启用")
        return NullSearch()
    if not settings.deepseek_api_key:
        log.info("没有 DeepSeek API Key，联网搜索不可用")
        return NullSearch()
    log.info("联网搜索已启用：DeepSeek 原生搜索")
    return DeepSeekSearch(settings)
