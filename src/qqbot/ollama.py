"""Ollama 守护：启动时确认本地模型服务在跑，不在就拉起来。

图片识别和向量检索都靠它，一旦它挂了不会报错，只会静默降级——
图片变「看不出来」、记忆召回退化成关键词。所以启动时主动检查一次。
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

# 常见安装位置，配置里没写时按顺序找
CANDIDATES = (
    Path(r"D:\dev\tools\ollama\ollama.exe"),
    Path(r"C:\Program Files\Ollama\ollama.exe"),
    Path(r"C:\Program Files (x86)\Ollama\ollama.exe"),
)


def _api_root(base_url: str) -> str:
    """把 http://127.0.0.1:11434/v1 变成 http://127.0.0.1:11434。"""
    parsed = urlparse(base_url or "")
    if not parsed.scheme or not parsed.netloc:
        return "http://127.0.0.1:11434"
    return f"{parsed.scheme}://{parsed.netloc}"


def _find_exe(configured: str) -> Path | None:
    if configured:
        path = Path(configured)
        if path.exists():
            return path
        log.warning("配置的 Ollama 路径不存在：%s", configured)
        return None

    found = shutil.which("ollama")
    if found:
        return Path(found)
    for candidate in CANDIDATES:
        if candidate.exists():
            return candidate
    return None


async def _alive(root: str, timeout: float = 2.0) -> bool:
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            resp = await client.get(f"{root}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


async def ensure_ollama(settings) -> bool:
    """确保 Ollama 可用。返回 True 表示最终能连上。"""
    if not getattr(settings, "ollama_autostart", True):
        return True

    root = _api_root(settings.embedding_base_url)
    if await _alive(root):
        log.info("Ollama 在线：%s", root)
        return True

    exe = _find_exe(getattr(settings, "ollama_exe", ""))
    if exe is None:
        log.warning(
            "Ollama 没在跑，也找不到可执行文件。图片识别和向量检索会降级。"
            " 在 .env 里设 OLLAMA_EXE 指到 ollama.exe。"
        )
        return False

    log.warning("Ollama 没在跑，尝试启动：%s", exe)
    try:
        kwargs: dict = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        subprocess.Popen([str(exe), "serve"], **kwargs)  # noqa: S603
    except Exception:
        log.exception("启动 Ollama 失败")
        return False

    # 首次加载要几秒到十几秒，最多等 30 秒
    for _ in range(30):
        await asyncio.sleep(1)
        if await _alive(root):
            log.info("Ollama 已启动：%s", root)
            return True

    log.warning("Ollama 启动后 30 秒内没连上，图片识别会继续降级")
    return False
