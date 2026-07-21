# outlook-ews-manager

[中文](README.md) | **English**

Read, search, forward, and send email on **Microsoft 365 operated by 21Vianet (世纪互联)** — the sovereign-cloud edition served from `partner.outlook.cn` — when your tenant has **disabled IMAP**. Ships as a zero-dependency Python CLI plus an agent skill (SKILL.md) that works with **Kimi Code, OpenAI Codex, Claude Code**, and any SKILL.md-compatible runtime.

## The problem

Your company mailbox shows `AUTHENTICATE failed` in every IMAP client, even with the correct password. The cause is usually a tenant-level IMAP block (`Set-CASMailbox -ImapEnabled $false` or an authentication policy), not a wrong password. But **EWS (Exchange Web Services) with OAuth typically stays open** — which is how clients like Foxmail keep working. This tool takes that route:

| Channel | Protocol | Auth | Used for |
|---|---|---|---|
| EWS | SOAP over HTTPS | OAuth2 device-code flow, rolling refresh token | check / search / read / download attachments / **native forward** |
| SMTP | STARTTLS, port 587 | password | sending new mail |

Forwarding uses the native EWS `ForwardItem`, so the original message chain and all attachments are preserved and Outlook recognizes it as a real forward.

## Install

Requires Python 3.7+ (standard library only, no pip install needed). Copy the folder into any skill directory:

| Runtime | Path |
|---|---|
| Kimi Code | `~/.kimi-code/skills/outlook-ews-manager/` |
| Codex CLI | `~/.codex/skills/outlook-ews-manager/` |
| Claude Code | `~/.claude/skills/outlook-ews-manager/` |
| Universal | `~/.agents/skills/outlook-ews-manager/` |

Or just use it as a plain CLI — the scripts run anywhere.

## Quick start

```bash
cd outlook-ews-manager
cp .env.example .env      # fill in SMTP user/password and EWS_USER
python3 scripts/setup.py  # one-time: SMTP check + browser OAuth (device code)
```

Credentials are stored locally with owner-only permissions (`chmod 600`): SMTP password in `.env`, refresh token in `token.json` (atomic, lock-protected writes; rolls over roughly every 90 days). **After setup, every command runs directly with no repeated checks** — re-run `setup.py` only if a command reports auth failure.

```bash
python3 scripts/ews.py check --limit 10              # latest mail (* = unread)
python3 scripts/ews.py search --from boss@corp.com   # server-side search
python3 scripts/ews.py fetch 1                       # read body
python3 scripts/ews.py download 1 --dir ~/Downloads  # attachments
python3 scripts/ews.py forward 1 --to x@y.com        # preview; add --confirm-send to send
python3 scripts/smtp.py send --to x@y.com --subject "Hi" --body "Hello"
```

Sending and forwarding are two-stage by design: preview first, send only after explicit confirmation. Full usage in [SKILL.md](SKILL.md); hard-won troubleshooting notes (IMAP diagnosis, device-code endpoint quirks, EWS namespaces) in [references/troubleshooting.md](references/troubleshooting.md).

## FAQ

**Why does IMAP fail with the right password?**
The tenant disabled IMAP at the mailbox or org level. Test the same password against SMTP — if SMTP works and IMAP doesn't, it's a policy block, not a credential problem. See [troubleshooting §2](references/troubleshooting.md).

**Do I need to register an Azure app?**
No. The OAuth flow uses the pre-provisioned Azure CLI public client ID, which exists in every sovereign cloud including 21Vianet's.

**Does it work with global Microsoft 365 (outlook.com)?**
It's built and verified against 21Vianet's 世纪互联 endpoints (`login.chinacloudapi.cn`, `partner.outlook.cn`). Global-cloud endpoints are not currently wired in.

**Is it safe to let an AI agent use this?**
The skill encodes guardrails: email content is treated as untrusted input, sends/forwards require a preview-then-confirm step, downloads never overwrite existing files, and credentials never leave the two local files.

## Development

```bash
python3 -m pytest tests/          # offline unit tests, no mailbox needed
python3 -m py_compile scripts/*.py
```

## License

[MIT](LICENSE)
