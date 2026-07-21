#!/usr/bin/env python3
# EWS 收信工具 —— 适配世纪互联版 M365（IMAP 被禁用时走 Exchange Web Services）。
#
# 用法:
#   python3 ews.py check [--limit 10] [--unseen]
#   python3 ews.py search [--from X] [--subject X] [--days N] [--limit 20]
#   python3 ews.py fetch <序号>          # 序号来自最近一次 check/search 的输出
#   python3 ews.py download <序号> --dir <目录>
#   python3 ews.py forward <序号> --to a@b.com [--confirm-send]
#   python3 ews.py folders
#
# 配置：首次使用先跑 scripts/setup.py（一次性授权），之后本脚本直接可用。
# 模块分工：mailconfig（配置与凭据）/ ews_session（token 与传输）/
#           soap（SOAP 请求构造）/ message（EWS 响应解析）。
import argparse, base64, json, os, sys, xml.etree.ElementTree as ET

import mailconfig as mc
import ews_session
import soap
from soap import T, M
import message

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".ews_cache.json")

def find_items(session, folder="inbox", limit=10, unseen=False, days=None, from_=None, subject=None):
    xml = soap.find_item_xml(folder=folder, limit=limit, unseen=unseen,
                             days=days, from_=from_, subject=subject)
    root = ET.fromstring(session.call(xml))
    return [message.parse_message(el) for el in root.iter(T + "Message")]

def save_cache(items):
    json.dump([[i.id, i.change_key] for i in items], open(CACHE, "w"))

def _cache_entry(n):
    """序号 → (ItemId, ChangeKey)；兼容旧格式缓存（纯 id 列表，ChangeKey 为空）。"""
    if os.path.exists(CACHE):
        ids = json.load(open(CACHE))
        if 1 <= n <= len(ids):
            e = ids[n - 1]
            if isinstance(e, list):
                return e[0], (e[1] if len(e) > 1 else "")
            return e, ""
    return None, ""

def resolve_id(n):
    """序号 → ItemId；无效返回 None，由调用方决定退出方式。"""
    return _cache_entry(n)[0]

def require_id(n):
    iid = resolve_id(n)
    if iid is None:
        sys.exit("序号 %s 无效，请先运行 check 或 search" % n)
    return iid

def get_item(session, iid, full=False):
    return ET.fromstring(session.call(soap.get_item_xml(iid, full)))

def print_list(items):
    for i, m in enumerate(items, 1):
        flag = "*" if m.unread else " "
        att = " [有附件]" if m.has_attachments else ""
        print("%2d. %s [%s] %s\n      %s%s" % (i, flag, m.date, m.from_name, m.subject, att))

def cmd_check(args, session):
    items = find_items(session, limit=args.limit, unseen=args.unseen)
    save_cache(items)
    if not items:
        print("没有符合条件的邮件"); return
    print_list(items)
    print("\n共 %d 封（* 未读）。用 fetch <序号> 查看正文" % len(items))

def cmd_search(args, session):
    # 过滤条件全部下推服务端（Contains Restriction），不再客户端内存筛，老邮件不会漏
    items = find_items(session, limit=args.limit, days=args.days,
                       from_=args.from_, subject=args.subject)
    save_cache(items)
    if not items:
        print("没有匹配的邮件"); return
    print_list(items)
    print("\n共 %d 封。用 fetch <序号> 查看正文" % len(items))

def cmd_fetch(args, session):
    root = get_item(session, require_id(args.id), full=True)
    m = message.parse_message(next(root.iter(T + "Message")))
    print("主题:", m.subject)
    print("发件人:", m.from_name, "<" + m.from_addr + ">")
    print("时间:", m.date)
    print("\n" + (m.body or "(无正文)"))
    if m.attachments:
        print("\n附件:")
        for a in m.attachments:
            print(" -", a.name)

def _safe_name(name):
    name = name.replace("\\", "_").replace("/", "_")
    name = "".join("_" if (ord(c) < 32 or c in '<>:"|?*') else c for c in name)
    return name.strip().strip(".") or "attachment"

def _unique_path(dirpath, name):
    base, ext = os.path.splitext(name)
    cand = os.path.join(dirpath, name)
    i = 1
    while os.path.exists(cand):
        cand = os.path.join(dirpath, "%s_%d%s" % (base, i, ext))
        i += 1
    return cand

def cmd_download(args, session):
    root = get_item(session, require_id(args.id), full=True)
    m = message.parse_message(next(root.iter(T + "Message")))
    if not m.attachments:
        print("该邮件没有附件"); return
    os.makedirs(args.dir, exist_ok=True)
    for a in m.attachments:
        groot = ET.fromstring(session.call(soap.get_attachment_xml(a.id)))
        fa = next(groot.iter(T + "FileAttachment"))
        content = fa.findtext(T + "Content")
        path = _unique_path(args.dir, _safe_name(a.name))
        with open(path, "wb") as f:
            f.write(base64.b64decode(content))
        print("已下载:", path)

def cmd_folders(args, session):
    root = ET.fromstring(session.call(soap.find_folder_xml()))
    for f in root.iter(T + "Folder"):
        print("- %s (%s 封)" % (f.findtext(T + "DisplayName"), f.findtext(T + "TotalCount")))

def cmd_forward(args, session):
    change_key = None
    if args.id_is_raw:
        iid = args.id
    else:
        try:
            n = int(args.id)
        except ValueError:
            sys.exit("序号无效，请先 check/search 后用序号，或加 --id-is-raw 直接传 ItemId")
        iid, change_key = _cache_entry(n)
        if iid is None:
            sys.exit("序号 %s 不在缓存中，请先运行 check 或 search" % n)
    to_list = [x.strip() for x in args.to.split(",") if x.strip()]
    if not to_list:
        sys.exit("收件人为空，请检查 --to 参数")
    cc_list = [x.strip() for x in args.cc.split(",") if x.strip()] if args.cc else []
    body_text = args.body or ""
    if args.body_file:
        body_text = open(args.body_file, encoding="utf-8").read()
    if args.html or (args.body_file or "").endswith(".html"):
        body_type = "HTML"      # 用户提供的 HTML，原样透传
    else:
        # 默认 HTML：纯文本说明转义 + 换行转 <br>。
        # 若用 Text，Exchange 会把整封转发（含原邮件 HTML 表格）摊平成纯文本。
        body_type = "HTML"
        if body_text:
            body_text = soap.esc(body_text).replace("\n", "<br>")

    # 一次 GetItem(full) 拿主题与附件清单（只取元数据，内容发送时按需拉）。
    # 实测：SendAndSaveCopy 的 ForwardItem 会丢文件附件；SaveOnly 草稿会
    # 自动物化原附件，缺失的再用 CreateAttachment 补齐（去重后通常为零）。
    src_subj = "(未知)"
    src_atts = []
    att_note = "无"
    try:
        root = get_item(session, iid, full=True)
        src = message.parse_message(next(root.iter(T + "Message")))
        src_subj = src.subject
        src_atts = src.attachments
        if src_atts:
            att_note = "%d 个，随转发携带（%s）" % (
                len(src_atts), ", ".join(a.name for a in src_atts))
    except Exception as e:
        att_note = "获取失败（%s），将以不带附件转发" % e
    subj = args.subject or ("FW: " + src_subj)

    print("=" * 60)
    print("转发预览（未发送）")
    print("=" * 60)
    print("源邮件主题: %s" % src_subj)
    print("转发主题  : %s" % subj)
    print("收件人    : %s" % ", ".join(to_list))
    if cc_list:
        print("抄送      : %s" % ", ".join(cc_list))
    print("正文格式  : %s" % body_type)
    print("正文长度  : %d 字符" % len(body_text))
    print("原邮件附件: %s" % att_note)
    print("-" * 60)
    if body_text:
        preview = body_text[:500] + ("...（截断）" if len(body_text) > 500 else "")
        print("正文预览:\n%s" % preview)
        print("-" * 60)

    if not args.confirm_send:
        print("\n[预览模式] 邮件未发送。确认无误后加 --confirm-send 重新运行以真正发送。")
        return

    def _noerror(resp, stage):
        rc = ET.fromstring(resp).find(".//" + M + "ResponseCode")
        if rc is None or rc.text != "NoError":
            print("\n[%s 失败] EWS 返回:\n%s" % (stage, resp[:1000]))
            sys.exit(1)

    try:
        if not src_atts:
            # 无附件：单发 SendAndSaveCopy
            resp = session.call(soap.forward_xml(
                iid, to_list, cc_list, subj, body_text, body_type, change_key=change_key))
            _noerror(resp, "发送")
        else:
            # 有附件：SaveOnly 草稿（原附件自动物化）→ 缺失的用 CreateAttachment 补齐 → SendItem
            resp = session.call(soap.forward_xml(
                iid, to_list, cc_list, subj, body_text, body_type,
                change_key=change_key, disposition="SaveOnly"))
            _noerror(resp, "创建草稿")
            did, dck = message.parse_created_item_id(ET.fromstring(resp))
            droot = get_item(session, did, full=True)
            draft_names = [a.name for a in message.parse_message(
                next(droot.iter(T + "Message"))).attachments]
            for a in src_atts:
                if a.name in draft_names:
                    draft_names.remove(a.name)   # 草稿已物化，跳过（按名单逐个去重）
                    continue
                groot = ET.fromstring(session.call(soap.get_attachment_xml(a.id)))
                fa = next(groot.iter(T + "FileAttachment"))
                resp = session.call(soap.create_attachment_xml(
                    did, a.name, fa.findtext(T + "Content") or ""))
                _noerror(resp, "挂载附件 " + a.name)
                did, dck = message.parse_attachment_root(ET.fromstring(resp))
            resp = session.call(soap.send_item_xml(did, dck))
            _noerror(resp, "发送")
        print("\n[已发送] EWS ForwardItem 原生转发完成，原邮件链及附件已保留。")
    except SystemExit:
        raise
    except Exception as e:
        print("\n[发送异常] %s" % e)
        sys.exit(1)

def main():
    ap = argparse.ArgumentParser(description="EWS 收信与转发工具（世纪互联 M365）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check");    p.add_argument("--limit", type=int, default=10); p.add_argument("--unseen", action="store_true"); p.set_defaults(fn=cmd_check)
    p = sub.add_parser("search");   p.add_argument("--from", dest="from_"); p.add_argument("--subject"); p.add_argument("--days", type=int); p.add_argument("--limit", type=int, default=20); p.set_defaults(fn=cmd_search)
    p = sub.add_parser("fetch");    p.add_argument("id", type=int); p.set_defaults(fn=cmd_fetch)
    p = sub.add_parser("download"); p.add_argument("id", type=int); p.add_argument("--dir", required=True); p.set_defaults(fn=cmd_download)
    p = sub.add_parser("folders");  p.set_defaults(fn=cmd_folders)
    p = sub.add_parser("forward"); p.add_argument("id"); p.add_argument("--id-is-raw", action="store_true"); p.add_argument("--to", required=True); p.add_argument("--cc"); p.add_argument("--subject"); p.add_argument("--body"); p.add_argument("--body-file"); p.add_argument("--html", action="store_true"); p.add_argument("--confirm-send", action="store_true"); p.set_defaults(fn=cmd_forward)
    args = ap.parse_args()
    session = ews_session.open_session(mc.load_config())
    args.fn(args, session)

if __name__ == "__main__":
    main()
