import os, sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """隔离的凭据目录：.env / token.json 都落在 tmp_path。"""
    monkeypatch.setenv("WORKING_EMAIL_HOME", str(tmp_path))
    return tmp_path


# ---------- 共享 fixture：EWS 响应样本 + 假 session ----------

FINDITEM_RESPONSE = """<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
 xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
 xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
<soap:Body><m:FindItemResponse><m:ResponseMessages><m:FindItemResponseMessage ResponseClass="Success">
<m:ResponseCode>NoError</m:ResponseCode><m:RootFolder TotalItemsInView="2" IncludesLastItemInRange="true"><t:Items>
<t:Message>
<t:ItemId Id="ID_A" ChangeKey="k1"/>
<t:Subject>Q3 周报</t:Subject>
<t:From><t:Mailbox><t:Name>老板</t:Name><t:EmailAddress>boss@corp.com</t:EmailAddress></t:Mailbox></t:From>
<t:DateTimeReceived>2026-07-20T09:00:00Z</t:DateTimeReceived>
<t:IsRead>false</t:IsRead>
<t:HasAttachments>true</t:HasAttachments>
</t:Message>
<t:Message>
<t:ItemId Id="ID_B" ChangeKey="k2"/>
<t:Subject>午餐拼单</t:Subject>
<t:From><t:Mailbox><t:Name>同事</t:Name><t:EmailAddress>pal@corp.com</t:EmailAddress></t:Mailbox></t:From>
<t:DateTimeReceived>2026-07-19T12:00:00Z</t:DateTimeReceived>
<t:IsRead>true</t:IsRead>
<t:HasAttachments>false</t:HasAttachments>
</t:Message>
</t:Items></m:RootFolder></m:FindItemResponseMessage></m:ResponseMessages></m:FindItemResponse>
</soap:Body></soap:Envelope>"""


class StubSession:
    """假 EWS session：记录发出的 XML，依次返回排队响应（单个值则反复返回）。"""

    def __init__(self, responses):
        if isinstance(responses, str):
            responses = [responses]
        self._responses = list(responses)
        self.sent = []

    def call(self, xml):
        self.sent.append(xml)
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]




GETITEM_RESPONSE = """<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
 xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
 xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
<soap:Body><m:GetItemResponse><m:ResponseMessages><m:GetItemResponseMessage ResponseClass="Success">
<m:ResponseCode>NoError</m:ResponseCode><m:Items>
<t:Message>
<t:ItemId Id="ID_A" ChangeKey="k1"/>
<t:Subject>Q3 周报</t:Subject>
<t:From><t:Mailbox><t:Name>老板</t:Name><t:EmailAddress>boss@corp.com</t:EmailAddress></t:Mailbox></t:From>
<t:DateTimeReceived>2026-07-20T09:00:00Z</t:DateTimeReceived>
<t:Body BodyType="Text">本周进展如下，请查收附件。</t:Body>
<t:Attachments>
<t:FileAttachment><t:AttachmentId Id="ATT_1"/><t:Name>报表.xlsx</t:Name><t:Size>5</t:Size></t:FileAttachment>
<t:FileAttachment><t:AttachmentId Id="ATT_2"/><t:Name>报表.xlsx</t:Name><t:Size>5</t:Size></t:FileAttachment>
</t:Attachments>
</t:Message>
</m:Items></m:GetItemResponseMessage></m:ResponseMessages></m:GetItemResponse>
</soap:Body></soap:Envelope>"""


def getattachment_response(att_id, content_b64):
    """构造 GetAttachment 响应：Content 为 base64 文本。"""
    return ("""<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
 xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
 xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
<soap:Body><m:GetAttachmentResponse><m:ResponseMessages><m:GetAttachmentResponseMessage ResponseClass="Success">
<m:ResponseCode>NoError</m:ResponseCode><m:Attachments>
<t:FileAttachment><t:AttachmentId Id="%s"/><t:Content>%s</t:Content></t:FileAttachment>
</m:Attachments></m:GetAttachmentResponseMessage></m:ResponseMessages></m:GetAttachmentResponse>
</soap:Body></soap:Envelope>""" % (att_id, content_b64))
