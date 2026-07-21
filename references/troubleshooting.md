# 世纪互联 M365 邮件接入排坑指南

本文记录 email-manager（IMAP/SMTP）对接世纪互联版 M365 的真实验证过程与结论，供排查参考。

## 目录
1. 端点与架构
2. 坑 1：IMAP AUTHENTICATE failed ≠ 密码错误
3. 坑 2：Foxmail 能连不代表 IMAP 可用
4. 坑 3：设备码 v1 端点的参数名是 code
5. 坑 4：EWS 响应的元素命名空间是 t: 不是 m:
6. 坑 5：DateTimeReceived 必须显式请求
7. 坑 6：ForwardItem 的附件与 ChangeKey（转发三段式由来）
8. 完整打通步骤（验证过的顺序）
9. 令牌生命周期与运维

## 1. 端点与架构

| 用途 | 端点 | 认证 | 状态 |
|---|---|---|---|
| 发件 | smtp.partner.outlook.cn:587 (STARTTLS) | 账号密码基本认证 | 通常可用 |
| 收件 IMAP | partner.outlook.cn:993 | 基本认证 + XOAUTH2 | 租户级禁用时两者都拒 |
| 收件 EWS | partner.outlook.cn/EWS/Exchange.asmx | OAuth2 Bearer | 可用（本技能方案） |
| 登录服务 | login.chinacloudapi.cn | — | 设备码/令牌端点 |

## 2. 坑 1：IMAP AUTHENTICATE failed ≠ 密码错误

现象：`imap.js check` 报 `AUTHENTICATE failed`，换 LOGIN / AUTHENTICATE PLAIN 都一样。

判别方法：**用同一密码试 SMTP 登录**。SMTP 能过、IMAP 被拒 = 密码没问题，是租户在邮箱/组织级别禁用了 IMAP（`Set-CASMailbox -ImapEnabled $false` 或 Authentication Policy）。不要再让用户换密码、找应用专用密码，方向是错的。

服务器 `CAPABILITY` 里即使列着 `AUTH=PLAIN AUTH=XOAUTH2` 也不代表允许登录——能力声明是服务级的，禁用策略是邮箱/租户级的。

## 3. 坑 2：Foxmail 能连不代表 IMAP 可用

Foxmail 配世纪互联 M365 时走微软新式验证（OAuth），登录后本地保存的"很长的密码"实为授权令牌，底层走 Exchange/EWS 协议而非密码 IMAP。这提示：IMAP 被禁的租户，EWS + OAuth 往往仍然开放。

## 4. 坑 3：设备码 v1 端点的参数名是 code

轮询令牌时向 `https://login.chinacloudapi.cn/common/oauth2/token` 提交：
- `grant_type=urn:ietf:params:oauth:grant-type:device_code`
- `code=<device_code 的值>` ← 参数名叫 `code`，叫 `device_code` 会报 `AADSTS900144: must contain parameter: 'code'`
- `resource=https://partner.outlook.cn`

公共客户端用 Azure CLI 的 `04b07795-8ddb-461a-bbee-02f9e1bf7b46`（预置在各主权云），无需自注册应用。

## 5. 坑 4：EWS 响应的元素命名空间是 t: 不是 m:

FindItem 响应里邮件元素是 `<t:Message>`（types 命名空间），不是 `<m:Message>`（messages 命名空间，只用于请求/响应外壳）。解析时用 `.../2006/types` 命名空间遍历，否则列表为空且不报错。

## 6. 坑 5：DateTimeReceived 必须显式请求

`Default` ItemShape 不含 `DateTimeReceived`（只有 DateTimeSent/DateTimeCreated）。列表和取信都要在 `AdditionalProperties` 里显式加 `<t:FieldURI FieldURI="item:DateTimeReceived"/>`，否则时间为空。

## 7. 坑 6：ForwardItem 的附件与 ChangeKey

转发链路在这台服务器上的实测结论：

1. **`ReferenceItemId` 必须带 `ChangeKey`**，否则 `ErrorChangeKeyRequiredForWriteOperations`。所以 `check`/`search` 的序号缓存存的是 `[ItemId, ChangeKey]` 对。
2. **不允许在 CreateItem 里内联设置 `item:Attachments`**（`ErrorInvalidPropertySet`）。给邮件加附件只能对已存在的邮件走 `CreateAttachment` 操作。
3. **`SendAndSaveCopy` 一步发送的 ForwardItem 会丢掉原邮件的文件附件**（收到的邮件 `HasAttachments=false`）；但 **`SaveOnly` 存草稿的 ForwardItem 会自动物化原附件**（ItemAttachment 内嵌邮件在两种路径下都会自动携带）。所以带附件转发走三段式：`SaveOnly` 建草稿 → 读草稿附件清单、缺失的用 `CreateAttachment` 补齐（按名称去重，实测通常物化完整、补齐为零）→ `SendItem` 发送并存已发送。
4. **每次 `CreateAttachment` 都会改变父邮件的 ChangeKey**：响应里的 `RootItemChangeKey` 必须滚动更新，下一个附件或 `SendItem` 要用最新的，否则报 ChangeKey 过期类错误。

## 8. 完整打通步骤（验证过的顺序）

1. 填 `.env`（SMTP 五项 + EWS_USER）。
2. `python3 scripts/setup.py`：先验证 SMTP 握手登录（失败仅警告，不阻断），再弹设备码引导——用户在浏览器打开 `https://login.partner.microsoftonline.cn/device` 输码登录，refresh token 自动写入 `token.json`（600 权限）。
3. `python3 scripts/ews.py check` 验证收件。
4. 完成。之后所有收发行指令直接调脚本，无任何启动检测；仅在报"认证失效"时重跑 `setup.py`。

如果第 1 步 SMTP 也认证失败：检查密码（含域名拼写！）、是否开了 MFA（需应用专用密码）、管理员是否禁用了 SMTP AUTH。

## 9. 令牌生命周期与运维

- access token 有效期约 1 小时；脚本每次运行自动用 refresh token 换新，**不需要后台进程或定时任务**。
- refresh token 滚动续期（每次使用自动换新，flock + 原子写回 `token.json`），典型 90 天不用才过期。
- 失效场景：超期未用、管理员撤销授权、改密码触发令牌吊销（视策略）。失效后重跑 `scripts/setup.py` 即可。
- 凭证只存本地 `.env` 与 `token.json`（均 600 权限），两者都必须进 `.gitignore`，不随 skill 分发（分发用 `.env.example`）。
