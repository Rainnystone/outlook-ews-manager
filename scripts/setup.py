#!/usr/bin/env python3
# setup —— outlook-ews-manager 一次性初始化（取代旧的 ews_auth.py）。
#
# 做三件事，全部通过即初始化完成，之后日常命令零体检直接可用：
#   1. 校验 .env 配置齐全（SMTP 五项 + EWS_USER）
#   2. EWS OAuth 设备码授权（浏览器扫码登录一次），refresh token 写入 token.json
#   3. SMTP 握手 + 登录验证（不发信）
# 最后把 .env / token.json 权限收紧到 600。
#
# 用法: python3 scripts/setup.py
import json, os, smtplib, sys, time, urllib.request, urllib.parse, urllib.error

import mailconfig as mc


def post(url, params):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r), None
    except urllib.error.HTTPError as e:
        try:
            return None, json.loads(e.read().decode())
        except Exception:
            return None, {"error": "http_%s" % e.code}


def device_code_auth(client_id):
    """设备码流程。注意 v1 端点轮询参数名是 code，不是 device_code（AADSTS900144）。"""
    dc, err = post(mc.LOGIN_BASE + "/devicecode", {"client_id": client_id, "resource": mc.EWS_RESOURCE})
    if err:
        sys.exit("设备码申请失败: %s" % err)
    print("=" * 56)
    print("请在浏览器打开:  " + dc["verification_url"])
    print("输入授权码:      " + dc["user_code"])
    print("=" * 56)
    print("等待授权中（%d 分钟内有效）..." % (int(dc["expires_in"]) // 60))

    deadline = time.time() + int(dc["expires_in"])
    interval = int(dc.get("interval", 5))
    while time.time() < deadline:
        time.sleep(interval)
        tok, err = post(mc.LOGIN_BASE + "/token", {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": client_id,
            "code": dc["device_code"],
            "resource": mc.EWS_RESOURCE,
        })
        if tok:
            mc.save_refresh_token(tok["refresh_token"])
            print("[OK] EWS 授权成功，refresh token 已写入 " + mc.token_path())
            return
        if err and err.get("error") == "authorization_pending":
            continue
        sys.exit("授权失败: %s" % err)
    sys.exit("授权超时，请重新运行 setup")


def smtp_verify(cfg):
    """验证 SMTP 握手与登录。返回 True/False；连接与认证异常不抛出。"""
    host = cfg["SMTP_HOST"]
    port = int(cfg.get("SMTP_PORT", 587))
    try:
        s = smtplib.SMTP(host, port, timeout=30)
        try:
            s.ehlo()
            if cfg.get("SMTP_SECURE", "false").lower() != "true":
                s.starttls()
                s.ehlo()
            s.login(cfg["SMTP_USER"], cfg["SMTP_PASS"])
        finally:
            s.quit()
    except smtplib.SMTPAuthenticationError:
        print("[WARN] SMTP 登录被拒（535）——密码错误、开了 MFA（需应用专用密码）、"
              "或管理员禁用了 SMTP AUTH。发件通道不可用，收件通道不受影响。")
        return False
    except (OSError, smtplib.SMTPException) as e:
        print("[WARN] SMTP 连接失败：%s —— 检查 SMTP_HOST/SMTP_PORT。发件通道不可用。" % e)
        return False
    print("[OK] SMTP 握手与登录验证通过（%s:%s）" % (host, port))
    return True


ENV_TEMPLATE = """\
SMTP_HOST=smtp.partner.outlook.cn
SMTP_PORT=587
SMTP_SECURE=false
SMTP_USER=you@yourcompany.com
SMTP_PASS=你的邮箱密码
SMTP_FROM=you@yourcompany.com
EWS_USER=you@yourcompany.com
EWS_CLIENT_ID=04b07795-8ddb-461a-bbee-02f9e1bf7b46
"""


def main():
    if not os.path.exists(mc.env_path()):
        sys.exit("未找到 %s\n"
                 "若包内有 .env.example，复制它为 .env 并填入账号密码后重跑；\n"
                 "没有（部分分发渠道不打包该文件）则手动创建 .env，内容如下：\n\n%s"
                 % (mc.env_path(), ENV_TEMPLATE))
    cfg = mc.load_config()
    mc.require(cfg, ["SMTP_HOST", "SMTP_USER", "SMTP_PASS", "EWS_USER"],
               "请编辑 %s 补齐后重跑 setup" % mc.env_path())

    smtp_ok = smtp_verify(cfg)
    device_code_auth(cfg.get("EWS_CLIENT_ID", mc.DEFAULT_CLIENT_ID))

    mc.ensure_private(mc.env_path())
    print("\n初始化完成。.env 与 token.json 已收紧为仅本人可读（600）。")
    if not smtp_ok:
        print("注意：SMTP 未通过验证，smtp.py 发件将不可用；ews.py 收件/转发不受影响。")
    print("之后收发邮件直接用 ews.py / smtp.py，无需再运行本脚本；")
    print("仅当命令报认证失效（约 90 天未用或管理员撤销）时重跑 setup。")


if __name__ == "__main__":
    main()
