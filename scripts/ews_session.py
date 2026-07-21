#!/usr/bin/env python3
# ews_session —— EWS 会话：token 生命周期 + HTTP 传输的统一 seam。
#
# open_session(cfg) 完成：读 refresh token → 向 login 端点换新 access token →
# 滚动写回 token.json → 返回 Session。之后所有 EWS 调用走 session.call(xml)。
# 认证类失败（无 token / 刷新被拒 / 调用 401）统一在此映射为"重跑 setup.py"。
#
# opener 参数是传输层的注入点：生产默认 urllib.request.urlopen，
# 测试注入脚本化假响应，使命令逻辑可以离线测试。
import json, sys, urllib.request, urllib.error, urllib.parse

import mailconfig as mc

_UA = "outlook-ews-manager/1.0"


class Session:
    def __init__(self, access_token, opener=None):
        self._token = access_token
        self._opener = opener or urllib.request.urlopen

    def call(self, body_xml):
        req = urllib.request.Request(mc.EWS_ENDPOINT,
            data=body_xml.encode(), headers={
                "Content-Type": "text/xml; charset=utf-8",
                "Authorization": "Bearer " + self._token,
                "User-Agent": _UA})
        try:
            with self._opener(req, timeout=60) as r:
                return r.read().decode(errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 401:
                sys.exit("EWS 返回 401 —— access token 获取失败或授权被撤销，请重跑 scripts/setup.py")
            raise


def open_session(cfg, opener=None):
    opener = opener or urllib.request.urlopen
    rt = mc.load_refresh_token()
    if not rt:
        sys.exit("未找到 refresh token，请先运行 scripts/setup.py 完成一次性授权")
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "client_id": cfg.get("EWS_CLIENT_ID", mc.DEFAULT_CLIENT_ID),
        "refresh_token": rt,
        "resource": mc.EWS_RESOURCE,
    }).encode()
    req = urllib.request.Request(mc.LOGIN_BASE + "/token",
        data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with opener(req, timeout=30) as r:
            tok = json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit("refresh token 已被拒绝（HTTP %s）——授权已失效，请重跑 scripts/setup.py" % e.code)
    # 滚动刷新：新 refresh_token 原子写回 token.json，长期免登录
    if tok.get("refresh_token"):
        mc.save_refresh_token(tok["refresh_token"])
    return Session(tok["access_token"], opener)
