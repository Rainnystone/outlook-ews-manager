"""soap.py 的请求构造测试：全部经 ET 解析后断言结构，不只看子串。"""
import os, sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import soap

SOAP_NS = "{http://schemas.xmlsoap.org/soap/envelope/}"
T = "{http://schemas.microsoft.com/exchange/services/2006/types}"
M = "{http://schemas.microsoft.com/exchange/services/2006/messages}"


def test_envelope_wraps_body_with_namespaces():
    root = ET.fromstring(soap.envelope("<m:X/>"))
    assert root.tag == SOAP_NS + "Envelope"
    body = root.find(SOAP_NS + "Body")
    assert body is not None and body.find(M + "X") is not None


def test_find_item_xml_no_restriction_by_default():
    root = ET.fromstring(soap.find_item_xml())
    fi = root.find(".//" + M + "FindItem")
    assert fi is not None
    assert fi.find(M + "Restriction") is None
    assert fi.find(".//" + T + "DistinguishedFolderId").get("Id") == "inbox"
    assert fi.find(M + "IndexedPageItemView").get("MaxEntriesReturned") == "10"


def test_find_item_xml_all_conditions_and_escaped():
    root = ET.fromstring(soap.find_item_xml(
        folder="sentitems", limit=20, unseen=True, days=3,
        from_="a<b@corp.com", subject='周"报'))
    fi = root.find(".//" + M + "FindItem")
    and_el = fi.find(M + "Restriction/" + T + "And")
    assert and_el is not None
    # 未读 + 时间窗
    assert and_el.find(T + "IsEqualTo") is not None
    assert and_el.find(T + "IsGreaterThanOrEqualTo") is not None
    # 两个 Contains 条件；ET 解析后取到的是反转义值，能解析即证明原文转义正确
    contains = and_el.findall(T + "Contains")
    vals = {c.find(T + "FieldURI").get("FieldURI"): c.find(T + "Constant").get("Value")
            for c in contains}
    assert vals["message:From"] == "a<b@corp.com"
    assert vals["item:Subject"] == '周"报'
    assert fi.find(".//" + T + "DistinguishedFolderId").get("Id") == "sentitems"


def test_get_item_xml_full_shape():
    root = ET.fromstring(soap.get_item_xml("ID<1>", full=True))
    assert root.findtext(".//" + T + "BodyType") == "Text"
    assert root.find(".//" + T + "ItemId").get("Id") == "ID<1>"
    fields = [f.get("FieldURI") for f in root.findall(".//" + T + "AdditionalProperties/" + T + "FieldURI")]
    assert "item:Body" in fields and "item:Attachments" in fields and "item:DateTimeReceived" in fields


def test_get_item_xml_default_shape():
    root = ET.fromstring(soap.get_item_xml("ID1", full=False))
    assert root.findtext(".//" + T + "BaseShape") == "Default"
    assert root.find(".//" + T + "BodyType") is None


def test_get_attachment_xml_escapes_id():
    root = ET.fromstring(soap.get_attachment_xml('A"1&2'))
    assert root.find(".//" + T + "AttachmentId").get("Id") == 'A"1&2'


def test_find_folder_xml_targets_msgfolderroot():
    root = ET.fromstring(soap.find_folder_xml())
    assert root.find(".//" + M + "FindFolder") is not None
    assert root.find(".//" + T + "DistinguishedFolderId").get("Id") == "msgfolderroot"


def test_forward_xml_html_cdata_injection_safe():
    payload = 'a]]>b</t:NewBodyContent><evil/>'
    x = soap.forward_xml("ID1", ["a@b.com"], [], "S", payload, "HTML")
    # 整个 SOAP 信封必须仍是合法 XML，且注入内容原样落在 CDATA 文本里
    root = ET.fromstring(x)
    body = root.find(".//" + T + "NewBodyContent")
    assert body is not None and body.text == payload
    assert root.find(".//evil") is None


def test_forward_xml_escapes_fields():
    x = soap.forward_xml("ID<1>", ["a&b@c.com"], [], "S&T", "plain<&", "Text")
    assert 'Id="ID&lt;1&gt;"' in x
    assert "a&amp;b@c.com" in x
    assert "S&amp;T" in x
    assert "plain&lt;&amp;" in x


def test_forward_xml_omits_empty_subject_and_cc():
    x = soap.forward_xml("ID1", ["a@b.com"], [], None, "hi", "Text")
    assert "<t:Subject>" not in x
    assert "<t:CcRecipients>" not in x
    assert "<t:ToRecipients>" in x


def test_contains_restriction_escapes_value():
    c = soap.contains("item:Subject", 'a<b"&')
    assert 'ContainmentMode="Substring"' in c
    assert "a&lt;b&quot;&amp;" in c
    assert 'a<b"&' not in c


def test_forward_xml_reference_includes_change_key():
    x = soap.forward_xml("ID1", ["a@b.com"], [], None, "hi", "Text", change_key="CK<1>")
    root = ET.fromstring(x)
    ref = root.find(".//" + T + "ReferenceItemId")
    assert ref.get("Id") == "ID1"
    assert ref.get("ChangeKey") == "CK<1>"     # ET 解析到反转义值即证明原文转义正确


def test_forward_xml_without_attachments_has_no_element():
    x = soap.forward_xml("ID1", ["a@b.com"], [], None, "hi", "Text")
    root = ET.fromstring(x)
    assert root.find(".//" + T + "Attachments") is None


def test_forward_xml_saveonly_goes_to_drafts_without_attachments():
    x = soap.forward_xml("ID1", ["a@b.com"], [], None, "hi", "Text", disposition="SaveOnly")
    root = ET.fromstring(x)
    ci = root.find(".//" + M + "CreateItem")
    assert ci.get("MessageDisposition") == "SaveOnly"
    assert ci.find(".//" + T + "DistinguishedFolderId").get("Id") == "drafts"
    assert root.find(".//" + T + "Attachments") is None


def test_create_attachment_xml_structure_and_escaping():
    x = soap.create_attachment_xml('P"1', "报表<1>.xlsx", "aGVsbG8=")
    root = ET.fromstring(x)
    assert root.find(".//" + M + "ParentItemId").get("Id") == 'P"1'
    fa = root.find(".//" + T + "FileAttachment")
    assert fa.findtext(T + "Name") == "报表<1>.xlsx"
    assert fa.findtext(T + "Content") == "aGVsbG8="


def test_send_item_xml_structure_and_escaping():
    x = soap.send_item_xml('ID<1>', 'CK&2')
    root = ET.fromstring(x)
    si = root.find(".//" + M + "SendItem")
    assert si.get("SaveItemToFolder") == "true"
    iid = si.find(".//" + T + "ItemId")
    assert iid.get("Id") == "ID<1>" and iid.get("ChangeKey") == "CK&2"
    assert si.find(".//" + T + "DistinguishedFolderId").get("Id") == "sentitems"


def test_reply_xml_defaults_to_reply_to_item():
    x = soap.reply_xml("ID1", "你好<br>世界", "HTML", change_key="CK1")
    root = ET.fromstring(x)
    item = root.find(".//" + T + "ReplyToItem")
    assert item is not None
    assert root.find(".//" + T + "ReplyAllToItem") is None
    ref = item.find(T + "ReferenceItemId")
    assert ref.get("Id") == "ID1" and ref.get("ChangeKey") == "CK1"
    # 主题与收件人由服务器生成，不出现在 XML 里
    assert item.find(T + "Subject") is None
    assert item.find(T + "ToRecipients") is None
    # HTML 说明走 CDATA，正文原样保留
    nb = item.find(T + "NewBodyContent")
    assert nb.get("BodyType") == "HTML" and nb.text == "你好<br>世界"


def test_reply_xml_reply_all_switches_element():
    x = soap.reply_xml("ID1", "ok", "HTML", reply_all=True)
    root = ET.fromstring(x)
    assert root.find(".//" + T + "ReplyAllToItem") is not None
    assert root.find(".//" + T + "ReplyToItem") is None


def test_get_item_xml_full_requests_recipients():
    # reply-all 预览依赖 To/Cc；显式请求，不依赖 Default shape 的服务器差异
    root = ET.fromstring(soap.get_item_xml("ID1", full=True))
    fields = [f.get("FieldURI") for f in root.findall(".//" + T + "AdditionalProperties/" + T + "FieldURI")]
    assert "message:ToRecipients" in fields
    assert "message:CcRecipients" in fields
