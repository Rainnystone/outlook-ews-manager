#!/usr/bin/env python3
# mailconfig —— outlook-ews-manager 的统一配置与凭据层（唯一权威来源）。
#
# 解析顺序（前者优先）：
#   1. 环境变量（SMTP_* / EWS_*）
#   2. $WORKING_EMAIL_HOME 指向的目录（可选覆盖）
#   3. skill 根目录的 .env（本文件所在 scripts/ 的上一级）
#
# 凭据布局：
#   .env        配置 + SMTP 密码（chmod 600）
#   token.json  EWS refresh token（chmod 600，flock + 原子写回，防并发撕裂）
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)

DEFAULT_CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"  # Azure CLI 公共客户端，各主权云预置
EWS_ENDPOINT = "https://partner.outlook.cn/EWS/Exchange.asmx"
EWS_RESOURCE = "https://partner.outlook.cn"
LOGIN_BASE = "https://login.chinacloudapi.cn/common/oauth2"


def config_dir():
    return os.environ.get("WORKING_EMAIL_HOME") or SKILL_ROOT


def env_path():
    return os.path.join(config_dir(), ".env")


def token_path():
    return os.path.join(config_dir(), "token.json")


def _read_env_file(path):
    cfg = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg


def load_config(prefixes=("SMTP_", "EWS_")):
    """合并 .env 与环境变量；环境变量覆盖同名键。"""
    cfg = _read_env_file(env_path())
    for k, v in os.environ.items():
        if k.startswith(prefixes):
            cfg[k] = v
    return cfg


def _chmod_600(path):
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows 等不支持 POSIX 权限的平台：尽力而为


class _LockedFile:
    """token.json 的 flock 上下文；无 fcntl 的平台（Windows）退化为无锁，
    原子写（tmp + os.replace）仍保证读不到撕裂内容。"""

    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._fh = open(path, "a+", encoding="utf-8")
        try:
            import fcntl
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
        except ImportError:
            pass

    def __enter__(self):
        return self._fh

    def __exit__(self, *exc):
        self._fh.close()


def load_refresh_token():
    p = token_path()
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                rt = json.load(f).get("refresh_token")
            if rt:
                return rt
        except (ValueError, OSError):
            pass
    # 旧版兼容：refresh token 曾明文存于 .env 的 EWS_REFRESH_TOKEN，
    # 首次读取时一次性迁移到 token.json（0600），不改动 .env 本身。
    legacy = os.environ.get("EWS_REFRESH_TOKEN") or _read_env_file(env_path()).get("EWS_REFRESH_TOKEN")
    if legacy:
        save_refresh_token(legacy)
        return legacy
    return None


def save_refresh_token(token):
    """持锁读改写 + 原子替换 + 0600。两个进程同时刷新时后者覆盖前者，
    服务端滚动令牌场景下两份都是刚签发的新令牌，可安全落盘。"""
    p = token_path()
    with _LockedFile(p) as fh:
        fh.seek(0)
        try:
            data = json.load(fh)
        except ValueError:
            data = {}
        data["refresh_token"] = token
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, p)
    _chmod_600(p)


def ensure_private(path):
    """写凭据文件后调用：收紧权限到 600。"""
    _chmod_600(path)


def require(cfg, keys, hint):
    missing = [k for k in keys if not cfg.get(k)]
    if missing:
        sys.exit("缺少配置 %s —— %s" % (", ".join(missing), hint))
