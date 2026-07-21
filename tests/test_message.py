"""message.py 的响应解析测试：坑知识（t: 命名空间、字段回退）只在一处验证。"""
import os, sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import message
from conftest import FINDITEM_RESPONSE, GETITEM_RESPONSE
from soap import T


def _messages(xml):
    return list(ET.fromstring(xml).iter(T + "Message"))


def test_parse_message_list_shape():
    m1, m2 = [message.parse_message(el) for el in _messages(FINDITEM_RESPONSE)]
    assert m1.id == "ID_A"
    assert m1.subject == "Q3 周报"
    assert m1.from_name == "老板"
    assert m1.from_addr == "boss@corp.com"
    assert m1.date == "2026-07-20 09:00:00"
    assert m1.unread is True
    assert m1.has_attachments is True
    assert m2.unread is False and m2.has_attachments is False


def test_parse_message_missing_fields_get_defaults():
    el = ET.fromstring(
        '<t:Message xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">'
        '<t:ItemId Id="X"/></t:Message>')
    m = message.parse_message(el)
    assert m.id == "X"
    assert m.subject == "(无主题)"
    assert m.from_name == "?"
    assert m.from_addr == ""
    assert m.date == ""
    assert m.unread is False


def test_parse_message_full_shape_with_body_and_attachments():
    (el,) = _messages(GETITEM_RESPONSE)
    m = message.parse_message(el)
    assert m.body == "本周进展如下，请查收附件。"
    assert len(m.attachments) == 2
    assert m.attachments[0].id == "ATT_1" and m.attachments[0].name == "报表.xlsx"
    assert m.attachments[1].id == "ATT_2"


# ---------- 命令穿假 session（特性化测试，锁住行为后再接线） ----------

import base64, json
from types import SimpleNamespace

import ews
from conftest import StubSession, getattachment_response


def test_cmd_fetch_prints_message(home, capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(ews, "CACHE", str(tmp_path / "cache.json"))
    (tmp_path / "cache.json").write_text(json.dumps(["ID_A"]))
    stub = StubSession(GETITEM_RESPONSE)
    ews.cmd_fetch(SimpleNamespace(id=1), stub)
    out = capsys.readouterr().out
    assert "Q3 周报" in out and "boss@corp.com" in out
    assert "本周进展如下" in out
    assert "报表.xlsx" in out
    assert "item:Body" in stub.sent[0]


def test_cmd_download_saves_attachments_without_overwrite(home, monkeypatch, tmp_path):
    monkeypatch.setattr(ews, "CACHE", str(tmp_path / "cache.json"))
    (tmp_path / "cache.json").write_text(json.dumps(["ID_A"]))
    outdir = tmp_path / "dl"
    stub = StubSession([
        GETITEM_RESPONSE,
        getattachment_response("ATT_1", base64.b64encode(b"hello").decode()),
        getattachment_response("ATT_2", base64.b64encode(b"world").decode()),
    ])
    ews.cmd_download(SimpleNamespace(id=1, dir=str(outdir)), stub)
    assert (outdir / "报表.xlsx").read_bytes() == b"hello"
    assert (outdir / "报表_1.xlsx").read_bytes() == b"world"   # 同名加序号，不覆盖
    assert len(stub.sent) == 3                                # GetItem + 两次 GetAttachment
    assert "ATT_1" in stub.sent[1] and "ATT_2" in stub.sent[2]


def test_parse_message_captures_change_key():
    els = _messages(FINDITEM_RESPONSE)
    assert message.parse_message(els[0]).change_key == "k1"


CREATE_DRAFT_RESPONSE = """<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
 xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
 xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
<soap:Body><m:CreateItemResponse><m:ResponseMessages>
<m:CreateItemResponseMessage ResponseClass="Success"><m:ResponseCode>NoError</m:ResponseCode>
<m:Items><t:Message><t:ItemId Id="DRAFT_1" ChangeKey="CK_D1"/></t:Message></m:Items>
</m:CreateItemResponseMessage></m:ResponseMessages></m:CreateItemResponse>
</soap:Body></soap:Envelope>"""

CREATE_ATTACHMENT_RESPONSE = """<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
 xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
 xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
<soap:Body><m:CreateAttachmentResponse><m:ResponseMessages>
<m:CreateAttachmentResponseMessage ResponseClass="Success"><m:ResponseCode>NoError</m:ResponseCode>
<m:Attachments><t:FileAttachment><t:AttachmentId Id="A1" RootItemId="DRAFT_1" RootItemChangeKey="CK_D2"/></t:FileAttachment></m:Attachments>
</m:CreateAttachmentResponseMessage></m:ResponseMessages></m:CreateAttachmentResponse>
</soap:Body></soap:Envelope>"""


def test_parse_created_item_id():
    assert message.parse_created_item_id(ET.fromstring(CREATE_DRAFT_RESPONSE)) == ("DRAFT_1", "CK_D1")


def test_parse_attachment_root():
    assert message.parse_attachment_root(ET.fromstring(CREATE_ATTACHMENT_RESPONSE)) == ("DRAFT_1", "CK_D2")


def _ok_response(op):
    return ('<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"'
            ' xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">'
            '<soap:Body><m:%sResponse><m:ResponseMessages>'
            '<m:%sResponseMessage ResponseClass="Success">'
            '<m:ResponseCode>NoError</m:ResponseCode>'
            '</m:%sResponseMessage></m:ResponseMessages></m:%sResponse>'
            '</soap:Body></soap:Envelope>' % (op, op, op, op))


def _attach_ok(root_ck):
    return ('<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"'
            ' xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"'
            ' xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">'
            '<soap:Body><m:CreateAttachmentResponse><m:ResponseMessages>'
            '<m:CreateAttachmentResponseMessage ResponseClass="Success">'
            '<m:ResponseCode>NoError</m:ResponseCode>'
            '<m:Attachments><t:FileAttachment>'
            '<t:AttachmentId Id="AX" RootItemId="DRAFT_1" RootItemChangeKey="%s"/>'
            '</t:FileAttachment></m:Attachments>'
            '</m:CreateAttachmentResponseMessage></m:ResponseMessages>'
            '</m:CreateAttachmentResponse></soap:Body></soap:Envelope>' % root_ck)


GETITEM_NOATT = GETITEM_RESPONSE.replace(
    "<t:Attachments>" + GETITEM_RESPONSE.split("<t:Attachments>")[1].split("</t:Attachments>")[0] + "</t:Attachments>",
    "")



DRAFT_GETITEM_ONE_ATT = GETITEM_RESPONSE.replace(
    '<t:FileAttachment><t:AttachmentId Id="ATT_2"/><t:Name>报表.xlsx</t:Name><t:Size>5</t:Size></t:FileAttachment>',
    "")

def test_forward_with_attachments_goes_draft_attach_send(home, capsys, monkeypatch, tmp_path):
    """带附件转发三段式：SaveOnly 草稿 → CreateAttachment × 2 → SendItem（滚动 ChangeKey）。"""
    monkeypatch.setattr(ews, "CACHE", str(tmp_path / "cache.json"))
    stub = StubSession([
        FINDITEM_RESPONSE,                          # check 写缓存
        GETITEM_RESPONSE,                           # forward 读源邮件（主题+附件清单）
        CREATE_DRAFT_RESPONSE,                      # SaveOnly → DRAFT_1/CK_D1
        DRAFT_GETITEM_ONE_ATT,                      # 草稿已物化 1 个附件
        getattachment_response("ATT_2", "d29ybGQ="),  # 只拉缺失的那个
        _attach_ok("CK_D2"),
        _ok_response("SendItem"),
    ])
    ews.cmd_check(SimpleNamespace(limit=10, unseen=False), stub)
    capsys.readouterr()
    ews.cmd_forward(SimpleNamespace(
        id="1", id_is_raw=False, to="me@corp.com", cc=None, subject=None,
        body="fwd", body_file=None, html=False, confirm_send=True), stub)
    assert 'MessageDisposition="SaveOnly"' in stub.sent[2]
    # 草稿已含 1 个附件 → 只补缺失的 1 个，不重复挂载
    attach_calls = [x for x in stub.sent if "CreateAttachment" in x]
    assert len(attach_calls) == 1 and "d29ybGQ=" in attach_calls[0]
    assert "aGVsbG8=" not in attach_calls[0]
    assert "SendItem" in stub.sent[-1] and 'ChangeKey="CK_D2"' in stub.sent[-1]
    assert "[已发送]" in capsys.readouterr().out


def test_forward_without_attachments_single_call(home, capsys, monkeypatch, tmp_path):
    """无附件时仍走单发 SendAndSaveCopy。"""
    monkeypatch.setattr(ews, "CACHE", str(tmp_path / "cache.json"))
    stub = StubSession([FINDITEM_RESPONSE, GETITEM_NOATT, _ok_response("CreateItem")])
    ews.cmd_check(SimpleNamespace(limit=10, unseen=False), stub)
    capsys.readouterr()
    ews.cmd_forward(SimpleNamespace(
        id="1", id_is_raw=False, to="me@corp.com", cc=None, subject=None,
        body="fwd", body_file=None, html=False, confirm_send=True), stub)
    assert len(stub.sent) == 3
    assert 'MessageDisposition="SendAndSaveCopy"' in stub.sent[2]
    assert 'ChangeKey="k1"' in stub.sent[2]
    assert "[已发送]" in capsys.readouterr().out


def test_forward_defaults_to_html_body_preserving_line_breaks(home, capsys, monkeypatch, tmp_path):
    """默认（不传 --html）也应以 HTML 发送：原邮件 HTML 格式不被摊平，
    纯文本说明经转义且换行转 <br>，不丢换行、不引入注入。"""
    monkeypatch.setattr(ews, "CACHE", str(tmp_path / "cache.json"))
    stub = StubSession([FINDITEM_RESPONSE, GETITEM_NOATT, _ok_response("CreateItem")])
    ews.cmd_check(SimpleNamespace(limit=10, unseen=False), stub)
    capsys.readouterr()
    ews.cmd_forward(SimpleNamespace(
        id="1", id_is_raw=False, to="me@corp.com", cc=None, subject=None,
        body="第一行\n第二<b>行", body_file=None, html=False, confirm_send=True), stub)
    sent = stub.sent[2]
    assert 'NewBodyContent BodyType="HTML"' in sent
    assert "第一行<br>第二&lt;b&gt;行" in sent          # 换行保留 + HTML 注入被转义
    assert "第一行\n" not in sent
