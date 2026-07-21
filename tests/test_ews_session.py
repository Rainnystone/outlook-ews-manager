"""ews_session 的 seam 测试：假 opener 注入，不触网。"""
from conftest import FINDITEM_RESPONSE, StubSession
from types import SimpleNamespace
import io, json, os, sys
import urllib.error

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import mailconfig as mc
import ews_session
import ews


class FakeResp:
    """模拟 urlopen 的上下文管理器响应。"""

    def __init__(self, payload):
        self._buf = io.BytesIO(json.dumps(payload).encode())

    def __enter__(self):
        return self._buf

    def __exit__(self, *exc):
        return False


def test_open_session_happy_path(home):
    mc.save_refresh_token("RT-OLD")
    seen = {}

    def fake_opener(req, timeout=None):
        seen["url"] = req.full_url
        seen["body"] = req.data.decode()
        return FakeResp({"access_token": "AT-1", "refresh_token": "RT-NEW"})

    s = ews_session.open_session(mc.load_config(), opener=fake_opener)

    assert isinstance(s, ews_session.Session)
    assert "login.chinacloudapi.cn" in seen["url"]
    assert "refresh_token=RT-OLD" in seen["body"]
    # 滚动刷新：新 refresh token 已写回 token.json
    assert mc.load_refresh_token() == "RT-NEW"


def _http_error(code):
    return urllib.error.HTTPError("http://x", code, "err", {}, io.BytesIO(b"{}"))


def test_open_session_without_token_exits(home):
    with pytest.raises(SystemExit, match="setup.py"):
        ews_session.open_session(mc.load_config())


def test_open_session_refresh_rejected_exits(home):
    mc.save_refresh_token("RT-OLD")

    def bad_opener(req, timeout=None):
        raise _http_error(400)

    with pytest.raises(SystemExit, match="setup.py"):
        ews_session.open_session(mc.load_config(), opener=bad_opener)


def test_session_call_posts_to_ews_with_bearer(home):
    seen = {}

    def fake_opener(req, timeout=None):
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        return FakeResp({"ok": 1})

    s = ews_session.Session("AT-9", opener=fake_opener)
    out = s.call("<x/>")
    assert "partner.outlook.cn/EWS/Exchange.asmx" in seen["url"]
    assert seen["auth"] == "Bearer AT-9"
    assert out == '{"ok": 1}'


def test_session_call_401_exits(home):
    def bad_opener(req, timeout=None):
        raise _http_error(401)

    s = ews_session.Session("AT-9", opener=bad_opener)
    with pytest.raises(SystemExit, match="setup.py"):
        s.call("<x/>")


def test_cmd_check_lists_and_caches(home, capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(ews, "CACHE", str(tmp_path / "cache.json"))
    stub = StubSession(FINDITEM_RESPONSE)
    ews.cmd_check(SimpleNamespace(limit=10, unseen=False), stub)
    out = capsys.readouterr().out
    assert "Q3 周报" in out and "午餐拼单" in out
    assert json.loads(open(ews.CACHE).read()) == [["ID_A", "k1"], ["ID_B", "k2"]]


def test_cmd_search_sends_contains_restriction(home, capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(ews, "CACHE", str(tmp_path / "cache.json"))
    stub = StubSession(FINDITEM_RESPONSE)
    ews.cmd_search(SimpleNamespace(limit=20, days=None, from_="boss<@corp", subject='周"报'), stub)
    xml = stub.sent[0]
    assert "<t:Contains" in xml and 'ContainmentMode="Substring"' in xml
    assert "boss&lt;@corp" in xml
    assert "周&quot;报" in xml
