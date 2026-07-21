# outlook-ews-manager

世纪互联版 Microsoft 365（partner.outlook.cn）邮箱命令行工具 + agent skill。EWS 收件/转发 + SMTP 发件，绕开租户级 IMAP 禁用。

## 架构速览（scripts/）

`ews.py`（命令编排）→ `ews_session.py`（token + 传输）→ `soap.py`（请求构造）/ `message.py`（响应解析）；`mailconfig.py`（配置与凭据）被前三者共用。改行为先跑 `python3 -m pytest tests/ -q`（32 个离线测试）。

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues, managed via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root, created lazily. See `docs/agents/domain.md`.
