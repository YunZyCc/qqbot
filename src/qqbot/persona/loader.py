from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_PERSONA = """你是「小毒」，一个住在 QQ 里的 AI 搭子，不是客服，也不是助手。
你幽默、偶尔毒舌、但在对方难受的时候很体贴。说话像微信聊天，短句、口语，不用 Markdown。"""

_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


@dataclass
class Persona:
    name: str
    text: str
    path: Path
    alias: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    description: str = ""


def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    match = _FRONTMATTER.match(raw)
    if not match:
        return {}, raw
    meta: dict = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key] = [
                item.strip().strip("'\"") for item in value[1:-1].split(",") if item.strip()
            ]
        else:
            meta[key] = value.strip("'\"")
    return meta, match.group(2)


def load_personas(directory: Path) -> dict[str, Persona]:
    """加载目录下所有 .md 人设，返回 名字/别名/文件名 → Persona 的映射。"""
    result: dict[str, Persona] = {}
    if not directory.exists():
        log.warning("人设目录不存在：%s", directory)
        return result

    for path in sorted(directory.glob("*.md")):
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            log.warning("读取人设失败：%s", path)
            continue
        meta, body = _parse_frontmatter(raw)
        text = body.strip() or raw.strip()
        if not text:
            continue
        persona = Persona(
            name=str(meta.get("name") or path.stem),
            text=text,
            path=path,
            alias=list(meta.get("alias") or []),
            tags=list(meta.get("tags") or []),
            description=str(meta.get("description") or ""),
        )
        for key in [persona.name, path.stem, *persona.alias]:
            result[key.lower()] = persona

    if result:
        log.info("加载了 %s 份人设：%s", len({p.path for p in result.values()}), "、".join(
            sorted({p.name for p in result.values()})
        ))
    return result


def load_persona(path: Path) -> str:
    """兼容旧接口：读单个文件，返回正文。"""
    if path.exists():
        raw = path.read_text(encoding="utf-8").strip()
        if raw:
            meta, body = _parse_frontmatter(raw)
            log.info("已加载人设文件 %s（%s）", path, meta.get("name", path.stem))
            return body.strip() or raw
    log.warning("未找到人设文件 %s，使用默认人设", path)
    return DEFAULT_PERSONA
