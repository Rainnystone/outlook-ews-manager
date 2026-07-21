"""纯函数与凭据层测试：不需要真实邮箱，不触网。"""
import json, os, stat, sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import mailconfig as mc
import ews


# ---------- mailconfig ----------

def test_env_parsing(home):
    (home / ".env").write_text(
        "SMTP_USER=a@b.com\n# comment\nBADLINE\nSMTP_PASS=x=y=z\n", encoding="utf-8")
    cfg = mc.load_config()
    assert cfg["SMTP_USER"] == "a@b.com"
    assert cfg["SMTP_PASS"] == "x=y=z"          # 值中的 = 不被截断
    assert "BADLINE" not in cfg


def test_env_var_overrides_file(home, monkeypatch):
    (home / ".env").write_text("EWS_USER=file@b.com\n", encoding="utf-8")
    monkeypatch.setenv("EWS_USER", "env@b.com")
    assert mc.load_config()["EWS_USER"] == "env@b.com"


def test_token_roundtrip_and_perms(home):
    assert mc.load_refresh_token() is None
    mc.save_refresh_token("RT-1")
    assert mc.load_refresh_token() == "RT-1"
    mode = stat.S_IMODE(os.stat(mc.token_path()).st_mode)
    assert mode == 0o600
    mc.save_refresh_token("RT-2")               # 滚动刷新覆盖
    assert mc.load_refresh_token() == "RT-2"


def test_token_corrupt_returns_none(home):
    (home / "token.json").write_text("not json", encoding="utf-8")
    assert mc.load_refresh_token() is None


def test_legacy_env_token_migrates(home):
    # 旧版 .env 里的 EWS_REFRESH_TOKEN 首次读取时迁移到 token.json
    (home / ".env").write_text("EWS_REFRESH_TOKEN=RT-LEGACY\n", encoding="utf-8")
    assert mc.load_refresh_token() == "RT-LEGACY"
    assert json.loads((home / "token.json").read_text())["refresh_token"] == "RT-LEGACY"
    mode = stat.S_IMODE(os.stat(mc.token_path()).st_mode)
    assert mode == 0o600


def test_require_missing_exits():
    with pytest.raises(SystemExit):
        mc.require({}, ["SMTP_HOST"], "hint")


# ---------- ews 纯函数 ----------

def test_safe_name_strips_illegal_chars():
    assert ews._safe_name('a/b\\c:d*e?"f<g>h|i.txt') == "a_b_c_d_e__f_g_h_i.txt"
    assert ews._safe_name("\x00\x01x") == "__x"
    assert ews._safe_name("...") == "attachment"
    assert ews._safe_name("") == "attachment"


def test_unique_path_never_overwrites(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"1")
    p1 = ews._unique_path(str(tmp_path), "a.pdf")
    assert p1.endswith("a_1.pdf")
    (tmp_path / "a_1.pdf").write_bytes(b"2")
    p2 = ews._unique_path(str(tmp_path), "a.pdf")
    assert p2.endswith("a_2.pdf")


def test_resolve_id_bounds(tmp_path, monkeypatch):
    monkeypatch.setattr(ews, "CACHE", str(tmp_path / "cache.json"))
    assert ews.resolve_id(1) is None            # 无缓存文件
    (tmp_path / "cache.json").write_text(json.dumps(["A", "B"]), encoding="utf-8")
    assert ews.resolve_id(2) == "B"
    assert ews.resolve_id(0) is None
    assert ews.resolve_id(3) is None
