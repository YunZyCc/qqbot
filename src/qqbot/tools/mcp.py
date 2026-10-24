from __future__ import annotations

import logging

from .registry import ToolRegistry

log = logging.getLogger(__name__)


async def load_mcp_tools(registry: ToolRegistry, servers: list[dict]) -> None:
    """MCP 工具加载骨架。

    配置为空时完全不生效。真正连接 MCP server 留到后续实现：
    需要安装 mcp 包，并为每个 server 管理子进程生命周期。
    """
    if not servers:
        return
    try:
        import mcp  # noqa: F401
    except ImportError:
        log.warning("未安装 mcp 包，跳过 MCP 工具加载")
        return

    for server in servers:
        name = server.get("name") or "unnamed"
        log.info("已读取 MCP server 配置：%s（连接逻辑待实现）", name)
