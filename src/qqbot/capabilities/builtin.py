from __future__ import annotations

from pydantic import BaseModel, Field

from ..core.message import build, seg_face, seg_mface, seg_record, seg_text
from .registry import Action, ActionRegistry


class SendTextParams(BaseModel):
    user_id: int
    text: str


class SendGroupTextParams(BaseModel):
    group_id: int
    text: str


class SendGroupSegmentsParams(BaseModel):
    group_id: int
    segments: list[dict]


class SendSegmentsParams(BaseModel):
    user_id: int
    segments: list[dict]


class SendFaceParams(BaseModel):
    user_id: int
    face_id: int


class SendMfaceParams(BaseModel):
    user_id: int
    file: str


class SendVoiceParams(BaseModel):
    user_id: int
    file: str


class SignatureParams(BaseModel):
    text: str


class QzoneParams(BaseModel):
    content: str
    images: list[str] = Field(default_factory=list)


class FriendRequestParams(BaseModel):
    flag: str
    approve: bool = True
    remark: str = ""


def register_builtin_actions(registry: ActionRegistry, ctx) -> None:
    """把平台驱动能力注册成 Action，内部代码和 LLM 工具共用这一套。"""
    api = ctx.api

    async def send_text(user_id: int, text: str):
        return await api.call("send_private_msg", user_id=user_id, message=[seg_text(text)])

    async def send_segments(user_id: int, segments: list[dict]):
        return await api.call("send_private_msg", user_id=user_id, message=build(segments))

    async def send_face(user_id: int, face_id: int):
        return await api.call("send_private_msg", user_id=user_id, message=[seg_face(face_id)])

    async def send_mface(user_id: int, file: str):
        return await api.call("send_private_msg", user_id=user_id, message=[seg_mface(file)])

    async def send_voice(user_id: int, file: str):
        return await api.call("send_private_msg", user_id=user_id, message=[seg_record(file)])

    async def send_group_text(group_id: int, text: str):
        return await api.call("send_group_msg", group_id=group_id, message=[seg_text(text)])

    async def send_group_segments(group_id: int, segments: list[dict]):
        return await api.call("send_group_msg", group_id=group_id, message=build(segments))

    async def set_signature(text: str):
        return await api.set_self_longnick(text)

    async def qzone_post(content: str, images: list[str]):
        return await api.send_qzone_msg(content, images or None)

    async def friend_request(flag: str, approve: bool, remark: str):
        return await api.call(
            "set_friend_add_request", flag=flag, approve=approve, remark=remark
        )

    registry.register(
        Action("send_text", "给指定 QQ 发一条文字消息", SendTextParams, send_text)
    )
    registry.register(
        Action("send_segments", "给指定 QQ 发消息段数组", SendSegmentsParams, send_segments)
    )
    registry.register(Action("send_face", "给指定 QQ 发 QQ 表情", SendFaceParams, send_face))
    registry.register(
        Action("send_mface", "给指定 QQ 发收藏表情包", SendMfaceParams, send_mface)
    )
    registry.register(Action("send_voice", "给指定 QQ 发语音", SendVoiceParams, send_voice))
    registry.register(
        Action("send_group_text", "往指定群发一条文字消息", SendGroupTextParams, send_group_text)
    )
    registry.register(
        Action(
            "send_group_segments",
            "往指定群发消息段数组",
            SendGroupSegmentsParams,
            send_group_segments,
        )
    )
    registry.register(
        Action("set_signature", "修改机器人个性签名", SignatureParams, set_signature)
    )
    registry.register(Action("qzone_post", "发布 QQ 空间说说", QzoneParams, qzone_post))
    registry.register(
        Action("friend_request", "同意或拒绝好友请求", FriendRequestParams, friend_request)
    )
