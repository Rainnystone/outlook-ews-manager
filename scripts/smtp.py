#!/usr/bin/env python3
# SMTP 发信工具（世纪互联 M365 / 任意标准 SMTP）。
# 用法:
#   python3 smtp.py send --to a@b.com --subject "主题" [--body "正文" | --body-file f] [--html] [--attach f1,f2] [--cc x] [--bcc y]
#   python3 smtp.py test            # 给自己发测试邮件
# 配置：.env 中 SMTP_HOST SMTP_PORT SMTP_SECURE SMTP_USER SMTP_PASS SMTP_FROM（首次先跑 scripts/setup.py 验证）
import argparse, os, smtplib, sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.header import Header
from email.utils import formataddr

import mailconfig as mc

def main():
    ap = argparse.ArgumentParser(description="SMTP 发信工具")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("send")
    p.add_argument("--to", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--body", default="")
    p.add_argument("--body-file")
    p.add_argument("--html", action="store_true")
    p.add_argument("--attach")
    p.add_argument("--cc"); p.add_argument("--bcc")
    sub.add_parser("test")
    args = ap.parse_args()

    cfg = mc.load_config()
    mc.require(cfg, ["SMTP_HOST", "SMTP_USER", "SMTP_PASS"],
               "请配置 .env 后先跑 scripts/setup.py 验证")
    user = cfg["SMTP_USER"]
    if args.cmd == "test":
        args.to, args.subject = user, "SMTP 测试"
        args.body = "SMTP 发送通道正常。"

    if getattr(args, "body_file", None):
        args.body = open(args.body_file, encoding="utf-8").read()
    subtype = "html" if getattr(args, "html", False) or (getattr(args, "body_file", None) or "").endswith(".html") else "plain"

    if getattr(args, "attach", None):
        msg = MIMEMultipart()
        msg.attach(MIMEText(args.body, subtype, "utf-8"))
        for f in args.attach.split(","):
            f = f.strip()
            with open(f, "rb") as fh:
                part = MIMEApplication(fh.read(), Name=os.path.basename(f))
            part["Content-Disposition"] = 'attachment; filename="%s"' % os.path.basename(f)
            msg.attach(part)
    else:
        msg = MIMEText(args.body, subtype, "utf-8")

    msg["Subject"] = Header(args.subject, "utf-8")
    msg["From"] = formataddr((str(Header(cfg.get("SMTP_FROM_NAME", user.split("@")[0]), "utf-8")), cfg.get("SMTP_FROM", user)))
    msg["To"] = args.to
    _cc = getattr(args, "cc", None)
    if _cc: msg["Cc"] = _cc

    try:
        s = smtplib.SMTP(cfg["SMTP_HOST"], int(cfg.get("SMTP_PORT", 587)), timeout=30)
        s.ehlo()
        if cfg.get("SMTP_SECURE", "false").lower() != "true":
            s.starttls(); s.ehlo()
        s.login(user, cfg["SMTP_PASS"])
    except smtplib.SMTPAuthenticationError:
        sys.exit("SMTP 登录被拒 —— 检查 .env 中 SMTP_PASS（若开启 MFA 需应用专用密码），改后重跑 scripts/setup.py 验证")
    except smtplib.SMTPNotSupportedError:
        sys.exit("服务器未声明 STARTTLS，按安全规则拒绝发送")
    except (OSError, smtplib.SMTPException) as e:
        sys.exit("SMTP 连接失败：%s —— 检查 .env 中 SMTP_HOST/SMTP_PORT" % e)
    rcpts = args.to.split(",") + (_cc.split(",") if _cc else []) + (getattr(args,"bcc",None).split(",") if getattr(args,"bcc",None) else [])
    s.sendmail(user, [r.strip() for r in rcpts], msg.as_string())
    s.quit()
    print("已发送 ->", args.to)

if __name__ == "__main__":
    main()
