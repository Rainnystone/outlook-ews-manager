# outlook-ews-manager

**中文** | [English](README.en.md)

在**世纪互联版 Microsoft 365**（21Vianet 运营，`partner.outlook.cn`）邮箱被租户禁用 IMAP 的情况下，照样收信、搜索、转发、发信。纯 Python 命令行工具 + agent skill（SKILL.md），兼容 **Kimi Code / Codex / Claude Code** 及所有遵循 SKILL.md 规范的 agent runtime，零第三方依赖。

## 解决什么问题

公司邮箱在所有 IMAP 客户端里都报 `AUTHENTICATE failed`，密码明明是对的。原因通常是租户在邮箱或组织级别禁用了 IMAP（`Set-CASMailbox -ImapEnabled $false` 或认证策略），不是密码错。但 **EWS（Exchange Web Services）+ OAuth 通常仍然开放**——Foxmail 就是这么绕的。本工具走同样的路：

| 通道 | 协议 | 认证 | 用途 |
|---|---|---|---|
| EWS | SOAP over HTTPS | OAuth2 设备码授权，refresh token 滚动续期 | 收件 / 搜索 / 读正文 / 下载附件 / **原生转发** |
| SMTP | STARTTLS，587 端口 | 账号密码 | 发新邮件 |

转发使用 EWS 原生 `ForwardItem`，自动保留完整邮件链与全部附件，Outlook 客户端能正确识别为转发。

## 安装

需要 Python 3.7+（只用标准库，无需 pip install）。把整个目录拷到任一 skill 路径：

| Runtime | 路径 |
|---|---|
| Kimi Code | `~/.kimi-code/skills/outlook-ews-manager/` |
| Codex CLI | `~/.codex/skills/outlook-ews-manager/` |
| Claude Code | `~/.claude/skills/outlook-ews-manager/` |
| 通用 | `~/.agents/skills/outlook-ews-manager/` |

也可以只当普通命令行工具用，脚本在任何目录都能跑。

## 快速开始

```bash
cd outlook-ews-manager
cp .env.example .env      # 填入 SMTP 账号密码、EWS_USER
python3 scripts/setup.py  # 一次性：SMTP 验证 + 浏览器扫码 OAuth 授权
```

凭据本地存放、仅本人可读（`chmod 600`）：SMTP 密码在 `.env`，refresh token 在 `token.json`（flock + 原子写回，约 90 天滚动续期）。**初始化后所有命令直接可用，不做重复检测**；仅当报"认证失效"时重跑 `setup.py`。

```bash
python3 scripts/ews.py check --limit 10              # 最新邮件（* 为未读）
python3 scripts/ews.py search --from boss@corp.com   # 服务端过滤搜索
python3 scripts/ews.py fetch 1                       # 读正文
python3 scripts/ews.py download 1 --dir ~/Downloads  # 下载附件
python3 scripts/ews.py reply 1 --body "收到"         # 原生回复（--all 回复全部，--attach 带附件）
python3 scripts/ews.py forward 1 --to x@y.com        # 转发预览；加 --confirm-send 才发送
python3 scripts/smtp.py send --to x@y.com --subject "主题" --body "正文"
```

发信与转发均为两段式：先预览，明确确认后才真正发送。完整用法见 [SKILL.md](SKILL.md)；踩坑记录（IMAP 判别、设备码端点参数名、EWS 命名空间等）见 [references/troubleshooting.md](references/troubleshooting.md)。

## 常见问题

**为什么密码正确 IMAP 也登录失败？**
租户在邮箱或组织级别禁用了 IMAP。用同一密码试 SMTP：SMTP 能过、IMAP 被拒 = 策略禁用，不是密码问题。详见[排坑指南 §2](references/troubleshooting.md)。

**需要自己注册 Azure 应用吗？**
不需要。OAuth 流程使用各主权云预置的 Azure CLI 公共客户端 ID，世纪互联环境同样可用。

**支持国际版 Microsoft 365（outlook.com）吗？**
本工具针对世纪互联端点（`login.chinacloudapi.cn`、`partner.outlook.cn`）开发与验证，暂未接入国际云端点。

**让 AI agent 操作邮箱安全吗？**
skill 内置防护规则：邮件内容按不可信输入处理、发信/转发强制先预览后确认、附件下载不覆盖已有文件、凭据只存在本地两个文件里不出仓。

## 开发

```bash
python3 -m pytest tests/          # 离线单元测试，不需要真实邮箱
python3 -m py_compile scripts/*.py
```

## License

[MIT](LICENSE)
