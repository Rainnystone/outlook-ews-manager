#!/usr/bin/env python3
# soap —— EWS SOAP 请求构造的唯一收口（出站方向）。
#
# 拥有三样东西：信封（SOAP_HEAD/TAIL）、命名空间常量（T/M，入站解析也从这里取）、
# 转义纪律（esc/contains/CDATA）。每个 builder 自己负责参数转义，
# 返回值保证是 ET.fromstring 可解析的合法 XML。
import xml.etree.ElementTree as ET  # noqa: F401  (供测试与调用方复用)

T = "{http://schemas.microsoft.com/exchange/services/2006/types}"
M = "{http://schemas.microsoft.com/exchange/services/2006/messages}"

_HEAD = ('<?xml version="1.0" encoding="utf-8"?>\n'
    '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" '
    'xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types" '
    'xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"><soap:Body>')
_TAIL = '</soap:Body></soap:Envelope>'


def envelope(inner):
    return _HEAD + inner + _TAIL


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def contains(field_uri, value):
    """服务端子串过滤（不区分大小写），值经 XML 转义。"""
    return ('<t:Contains ContainmentMode="Substring" ContainmentComparison="IgnoreCase">'
            '<t:FieldURI FieldURI="' + field_uri + '"/>'
            '<t:Constant Value="' + esc(value) + '"/></t:Contains>')


def find_item_xml(folder="inbox", limit=10, unseen=False, days=None, from_=None, subject=None):
    """FindItem（列表）：条件全部下推服务端，值经转义。"""
    conds = []
    if unseen:
        conds.append('<t:IsEqualTo><t:FieldURI FieldURI="message:IsRead"/>'
                     '<t:FieldURIOrConstant><t:Constant Value="false"/></t:FieldURIOrConstant></t:IsEqualTo>')
    if days:
        from datetime import datetime, timedelta, timezone
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conds.append('<t:IsGreaterThanOrEqualTo><t:FieldURI FieldURI="item:DateTimeReceived"/>'
                     '<t:FieldURIOrConstant><t:Constant Value="' + since + '"/></t:FieldURIOrConstant></t:IsGreaterThanOrEqualTo>')
    if from_:
        conds.append(contains("message:From", from_))
    if subject:
        conds.append(contains("item:Subject", subject))
    restriction = ""
    if conds:
        inner = conds[0] if len(conds) == 1 else "<t:And>" + "".join(conds) + "</t:And>"
        restriction = "<m:Restriction>" + inner + "</m:Restriction>"
    return envelope(
        '<m:FindItem Traversal="Shallow">'
        '<m:ItemShape><t:BaseShape>IdOnly</t:BaseShape><t:AdditionalProperties>'
        '<t:FieldURI FieldURI="item:Subject"/><t:FieldURI FieldURI="message:From"/>'
        '<t:FieldURI FieldURI="item:DateTimeReceived"/><t:FieldURI FieldURI="message:IsRead"/>'
        '<t:FieldURI FieldURI="item:HasAttachments"/></t:AdditionalProperties></m:ItemShape>'
        '<m:IndexedPageItemView MaxEntriesReturned="' + str(limit) + '" Offset="0" BasePoint="Beginning"/>'
        '<m:SortOrder><t:FieldOrder Order="Descending"><t:FieldURI FieldURI="item:DateTimeReceived"/></t:FieldOrder></m:SortOrder>'
        + restriction +
        '<m:ParentFolderIds><t:DistinguishedFolderId Id="' + esc(folder) + '"/></m:ParentFolderIds>'
        '</m:FindItem>')


def get_item_xml(iid, full=False):
    """GetItem：full=True 时显式请求正文/附件/接收时间（Default shape 不含这些）。"""
    if full:
        shape = ('<t:BaseShape>Default</t:BaseShape><t:AdditionalProperties>'
                 '<t:FieldURI FieldURI="item:Body"/><t:FieldURI FieldURI="item:Attachments"/>'
                 '<t:FieldURI FieldURI="item:DateTimeReceived"/>'
                 '<t:FieldURI FieldURI="message:ToRecipients"/>'
                 '<t:FieldURI FieldURI="message:CcRecipients"/>'
                 '</t:AdditionalProperties><t:BodyType>Text</t:BodyType>')
    else:
        shape = '<t:BaseShape>Default</t:BaseShape>'
    return envelope('<m:GetItem><m:ItemShape>' + shape + '</m:ItemShape>'
            '<m:ItemIds><t:ItemId Id="' + esc(iid) + '"/></m:ItemIds></m:GetItem>')


def get_attachment_xml(attachment_id):
    return envelope('<m:GetAttachment><m:AttachmentShape/>'
            '<m:AttachmentIds><t:AttachmentId Id="' + esc(attachment_id) + '"/></m:AttachmentIds>'
            '</m:GetAttachment>')


def find_folder_xml():
    return envelope('<m:FindFolder Traversal="Shallow">'
            '<m:FolderShape><t:BaseShape>Default</t:BaseShape></m:FolderShape>'
            '<m:ParentFolderIds><t:DistinguishedFolderId Id="msgfolderroot"/></m:ParentFolderIds>'
            '</m:FindFolder>')


def forward_xml(iid, to_list, cc_list, subject, body_text, body_type="HTML", change_key=None, disposition="SendAndSaveCopy"):
    """EWS 原生 ForwardItem：原邮件作为引用块附在 NewBodyContent 之后。
    这是真正的转发，不是 SMTP 手动拼正文。HTML 正文走 CDATA（]]> 拆段防撕破信封）。
    ReferenceItemId 必须带 ChangeKey（写操作要求），由缓存提供。
    disposition="SendAndSaveCopy" 直接发送并存已发送；"SaveOnly" 存草稿
    （挂附件走 create_attachment_xml + send_item_xml 的三段式）。"""
    def mailboxes(addrs):
        return "".join('<t:Mailbox><t:EmailAddress>%s</t:EmailAddress></t:Mailbox>' % esc(a) for a in addrs if a)
    to_xml = "<t:ToRecipients>" + mailboxes(to_list) + "</t:ToRecipients>" if to_list else ""
    cc_xml = "<t:CcRecipients>" + mailboxes(cc_list) + "</t:CcRecipients>" if cc_list else ""
    subj_xml = "<t:Subject>%s</t:Subject>" % esc(subject) if subject else ""
    if body_type == "HTML":
        safe_body = body_text.replace("]]>", "]]]]><![CDATA[>")
        new_body = '<t:NewBodyContent BodyType="HTML"><![CDATA[%s]]></t:NewBodyContent>' % safe_body
    else:
        new_body = '<t:NewBodyContent BodyType="Text">%s</t:NewBodyContent>' % esc(body_text)
    ck = ' ChangeKey="%s"' % esc(change_key) if change_key else ""
    folder = "sentitems" if disposition == "SendAndSaveCopy" else "drafts"
    return envelope(
        '<m:CreateItem MessageDisposition="' + disposition + '">'
        '<m:SavedItemFolderId><t:DistinguishedFolderId Id="' + folder + '"/></m:SavedItemFolderId>'
        '<m:Items><t:ForwardItem>' +
        subj_xml + to_xml + cc_xml +
        '<t:ReferenceItemId Id="%s"%s/>' % (esc(iid), ck) +
        new_body +
        '</t:ForwardItem></m:Items>'
        '</m:CreateItem>')


def create_attachment_xml(parent_id, name, content_b64):
    """给已存在的邮件（如转发草稿）追加文件附件。服务器拒绝 CreateItem 内联
    设置 item:Attachments（ErrorInvalidPropertySet），必须走本操作。"""
    return envelope('<m:CreateAttachment>'
        '<m:ParentItemId Id="' + esc(parent_id) + '"/>'
        '<m:Attachments><t:FileAttachment><t:Name>' + esc(name) + '</t:Name>'
        '<t:Content>' + content_b64 + '</t:Content></t:FileAttachment></m:Attachments>'
        '</m:CreateAttachment>')


def send_item_xml(iid, change_key):
    """发送草稿箱中的邮件，并存一份到已发送。"""
    return envelope('<m:SendItem SaveItemToFolder="true">'
        '<m:ItemIds><t:ItemId Id="' + esc(iid) + '" ChangeKey="' + esc(change_key) + '"/></m:ItemIds>'
        '<m:SavedItemFolderId><t:DistinguishedFolderId Id="sentitems"/></m:SavedItemFolderId>'
        '</m:SendItem>')


def reply_xml(iid, body_text, body_type="HTML", change_key=None, reply_all=False,
              disposition="SendAndSaveCopy"):
    """EWS 原生回复：ReplyToItem（回复发件人）/ ReplyAllToItem（回复全部）。
    主题与收件人由服务器生成（RE: 原主题；reply→发件人，reply-all→原 To+Cc 去自己），
    不在 XML 中出现。ReferenceItemId 必须带 ChangeKey（写操作要求）。
    带附件时用 disposition="SaveOnly" 建草稿，走 create_attachment_xml + send_item_xml。"""
    tag = "ReplyAllToItem" if reply_all else "ReplyToItem"
    if body_type == "HTML":
        safe_body = body_text.replace("]]>", "]]]]><![CDATA[>")
        new_body = '<t:NewBodyContent BodyType="HTML"><![CDATA[%s]]></t:NewBodyContent>' % safe_body
    else:
        new_body = '<t:NewBodyContent BodyType="Text">%s</t:NewBodyContent>' % esc(body_text)
    ck = ' ChangeKey="%s"' % esc(change_key) if change_key else ""
    folder = "sentitems" if disposition == "SendAndSaveCopy" else "drafts"
    return envelope(
        '<m:CreateItem MessageDisposition="' + disposition + '">'
        '<m:SavedItemFolderId><t:DistinguishedFolderId Id="' + folder + '"/></m:SavedItemFolderId>'
        '<m:Items><t:%s>' % tag +
        '<t:ReferenceItemId Id="%s"%s/>' % (esc(iid), ck) +
        new_body +
        '</t:%s></m:Items>' % tag +
        '</m:CreateItem>')
