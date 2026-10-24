from __future__ import annotations

from .chat import ChatModule
from .friends import FriendsModule
from .group import GroupModule
from .media import MediaModule
from .profile import ProfileModule
from .qzone import QzoneModule
from .self_memory import SelfMemoryModule

# 新功能模块加到这里；是否启用由 ENABLED_MODULES 决定
MODULES = [
    ChatModule(),
    GroupModule(),
    FriendsModule(),
    MediaModule(),
    QzoneModule(),
    ProfileModule(),
    SelfMemoryModule(),
]
