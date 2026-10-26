from __future__ import annotations

from .chat import ChatModule
from .diary import DiaryModule
from .friends import FriendsModule
from .maintenance import MaintenanceModule
from .media import MediaModule
from .proactive import ProactiveModule
from .profile import ProfileModule
from .qzone import QzoneModule
from .schedule import ScheduleModule
from .self_memory import SelfMemoryModule

# 新功能模块加到这里；是否启用由 ENABLED_MODULES 决定
# 群聊逻辑并进了 chat（群消息先记录、再按四级规则决定回不回），不再单独成模块
MODULES = [
    ChatModule(),
    DiaryModule(),
    ProactiveModule(),
    MaintenanceModule(),
    FriendsModule(),
    MediaModule(),
    QzoneModule(),
    ProfileModule(),
    SelfMemoryModule(),
    ScheduleModule(),
]
