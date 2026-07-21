#!/usr/bin/env python3
# message —— EWS 响应解析的唯一收口（入站方向）。
#
# 这里的每行都对应 troubleshooting.md 里踩过的坑，只写一次：
#   - 元素在 t:（types）命名空间，不是 m:（messages 只是外壳）  → §5
#   - DateTimeReceived 必须显式请求，且格式化为本地可读形式      → §6
#   - From 显示名缺失时回退到邮箱地址，再回退到 "?"
#   - IsRead / HasAttachments 是字符串 "true"/"false"，不是布尔
from dataclasses import dataclass, field

from soap import T


@dataclass
class Attachment:
    id: str = ""
    name: str = ""


@dataclass
class Message:
    id: str = ""
    change_key: str = ""
    subject: str = "(无主题)"
    from_name: str = "?"
    from_addr: str = ""
    date: str = ""
    unread: bool = False
    has_attachments: bool = False
    body: str = ""
    attachments: list = field(default_factory=list)


def _text(el, path):
    v = el.findtext(path)
    return v if v is not None else ""


def parse_created_item_id(root):
    """CreateItem(SaveOnly) 响应 → (ItemId, ChangeKey)，即转发草稿的句柄。"""
    el = root.find(".//" + T + "ItemId")
    return (el.get("Id", ""), el.get("ChangeKey", "")) if el is not None else ("", "")


def parse_attachment_root(root):
    """CreateAttachment 响应 → (RootItemId, RootItemChangeKey)。
    每次挂附件父邮件 ChangeKey 都会变，必须滚动更新后再发下一个/发送。"""
    el = root.find(".//" + T + "AttachmentId")
    return (el.get("RootItemId", ""), el.get("RootItemChangeKey", "")) if el is not None else ("", "")


def parse_message(el):
    """把 <t:Message> 元素解析为 Message；缺字段给默认值，不抛异常。"""
    m = Message()
    iid = el.find(T + "ItemId")
    if iid is not None:
        m.id = iid.get("Id", "")
        m.change_key = iid.get("ChangeKey", "")
    m.subject = (_text(el, T + "Subject").strip() or "(无主题)")
    frm = el.find(T + "From/" + T + "Mailbox")
    if frm is not None:
        m.from_name = _text(frm, T + "Name") or _text(frm, T + "EmailAddress") or "?"
        m.from_addr = _text(frm, T + "EmailAddress")
    m.date = _text(el, T + "DateTimeReceived")[:19].replace("T", " ")
    m.unread = _text(el, T + "IsRead") == "false"
    m.has_attachments = _text(el, T + "HasAttachments") == "true"
    m.body = _text(el, T + "Body").strip()
    for a in el.findall(T + "Attachments/" + T + "FileAttachment"):
        aid = a.find(T + "AttachmentId")
        m.attachments.append(Attachment(
            id=aid.get("Id", "") if aid is not None else "",
            name=_text(a, T + "Name") or "attachment"))
    return m
