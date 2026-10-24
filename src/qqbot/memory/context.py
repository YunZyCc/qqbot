"""当前工具调用所属的会话 scope。

SimpleRuntime 在执行工具前设置，工具 handler 读取；
这样工具不需要在参数里暴露 scope，也不会串会话。
"""

from contextvars import ContextVar

current_scope: ContextVar[str] = ContextVar("current_scope", default="")
