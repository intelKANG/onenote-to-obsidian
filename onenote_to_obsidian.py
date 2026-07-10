#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OneNote → Obsidian 迁移工具

把 OneNote 云端(能在 onenote.com 看到的)所有笔记本、分区、页面下载下来,
转成 Markdown 落到 Obsidian 库,并尽量保留原始创建/修改时间戳。

用法:
    python3 onenote_to_obsidian.py --output /path/to/vault/subfolder
    python3 onenote_to_obsidian.py -o ~/Documents/MyVault/OneNote迁移 --tenant common

参数:
    -o, --output       输出目录(必填)
    --tenant           consumers=个人号(默认) / common=支持公司学校号
    --client-id        自定义 client_id(默认用微软公开的 Graph CLI)
    --notebook         只迁移名称包含该文字的笔记本

依赖:
    - Python 3.8+
    - requests    (pip install requests)
    - pandoc      (macOS: brew install pandoc, Ubuntu: apt install pandoc,
                   Windows: 从 pandoc.org 下载安装包)
    - SetFile     (macOS 独有,用来恢复文件 birthtime;非 macOS 会自动跳过。
                   Mac 安装: xcode-select --install)
"""

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from html import unescape

try:
    import requests
except ImportError:
    print("❌ 缺少 requests,请先安装: pip3 install requests")
    sys.exit(1)


# ─── 常量 ─────────────────────────────────────────────────────────
# 微软官方公开的 Microsoft Graph CLI client_id,支持设备码流程
DEFAULT_CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
SCOPES = "Notes.Read offline_access"
BASE = "https://graph.microsoft.com/v1.0/me/onenote"
TOKEN_CACHE = pathlib.Path.home() / ".onenote_migrate_token.json"
IS_MAC = sys.platform == "darwin"


# ─── 依赖检测 ─────────────────────────────────────────────────────
def check_dependencies():
    """检查外部命令是否可用,缺失则报错退出"""
    if not shutil.which("pandoc"):
        print("❌ 缺少 pandoc")
        print("   macOS:   brew install pandoc")
        print("   Ubuntu:  sudo apt install pandoc")
        print("   Windows: https://pandoc.org/installing.html")
        sys.exit(1)

    if IS_MAC and not shutil.which("SetFile"):
        print("⚠️  未找到 SetFile(macOS 独有,用来恢复 birthtime)")
        print("   若需要保留创建时间,请运行: xcode-select --install")
        print("   否则脚本会继续,但只会保留修改时间。\n")


# ─── 设备码登录 ────────────────────────────────────────────────────
def save_token(t):
    """把 token 存到 ~/.onenote_migrate_token.json,权限 600"""
    t["expires_at"] = time.time() + t.get("expires_in", 3600)
    TOKEN_CACHE.write_text(json.dumps(t))
    try:
        os.chmod(TOKEN_CACHE, 0o600)
    except Exception:
        pass  # Windows 不支持 chmod,忽略


def device_login(client_id, tenant):
    """
    OAuth 2.0 Device Code Flow
    返回 access_token,支持从缓存续期
    """
    # 1) 尝试用缓存
    if TOKEN_CACHE.exists():
        try:
            d = json.loads(TOKEN_CACHE.read_text())
            if d.get("expires_at", 0) > time.time() + 60:
                return d["access_token"]
            if d.get("refresh_token"):
                r = requests.post(
                    f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                    data={
                        "client_id": client_id,
                        "grant_type": "refresh_token",
                        "refresh_token": d["refresh_token"],
                        "scope": SCOPES,
                    },
                )
                if r.status_code == 200:
                    t = r.json()
                    save_token(t)
                    return t["access_token"]
        except Exception:
            pass  # 缓存坏了就走完整登录

    # 2) 走完整设备码流程
    r = requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode",
        data={"client_id": client_id, "scope": SCOPES},
    )
    r.raise_for_status()
    d = r.json()

    print("\n" + "=" * 60)
    print(f"👉 浏览器打开: {d['verification_uri']}")
    print(f"👉 输入代码:   {d['user_code']}")
    print("=" * 60)
    print("授权完成后回到这里,脚本会自动继续...\n")

    while True:
        time.sleep(d["interval"])
        r = requests.post(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            data={
                "client_id": client_id,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": d["device_code"],
            },
        )
        j = r.json()
        if "access_token" in j:
            save_token(j)
            print("✅ 登录成功\n")
            return j["access_token"]
        if j.get("error") not in ("authorization_pending", "slow_down"):
            print(f"❌ 登录失败: {j}")
            sys.exit(1)


# ─── 工具函数 ─────────────────────────────────────────────────────
def sanitize(name):
    """清理文件/目录名的非法字符"""
    return re.sub(r'[\\/:*?"<>|#^\[\]]', "_", (name or "untitled").strip())[:120] or "untitled"


def gget(url, headers):
    """GET 请求,处理限流和临时服务故障。"""
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=60)
            if r.status_code == 429 or 500 <= r.status_code < 600:
                delay = int(r.headers.get("Retry-After", "5"))
                print(f"    ⚠️  API {r.status_code}, {delay} 秒后重试 ({attempt + 1}/3)")
                time.sleep(delay)
                continue
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == 2:
                raise
            print(f"    ⚠️  网络请求失败, 5 秒后重试 ({attempt + 1}/3)")
            time.sleep(5)
    r.raise_for_status()


def list_all(url, headers):
    """自动翻页,返回全部条目"""
    items = []
    while url:
        j = gget(url, headers).json()
        items.extend(j.get("value", []))
        url = j.get("@odata.nextLink")
    return items


def set_file_times(path, created_iso, modified_iso):
    """
    把文件系统的时间戳设成 OneNote 的原始时间
    - mtime: 所有平台都能改
    - birthtime: 只有 macOS 且装了 SetFile 才能改
    """
    def to_ep(value):
        value = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(value).timestamp()
        except ValueError:
            # Python 3.9 on macOS rejects some Graph timestamps with fractions.
            return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f%z").timestamp()

    m, c = to_ep(modified_iso), to_ep(created_iso)
    os.utime(path, (m, m))

    if IS_MAC and shutil.which("SetFile"):
        fmt = lambda ep: datetime.fromtimestamp(ep).strftime("%m/%d/%Y %H:%M:%S")
        subprocess.run(
            ["SetFile", "-d", fmt(c), "-m", fmt(m), str(path)],
            check=False,
            capture_output=True,
        )


def html_to_md(html):
    """pandoc: HTML → Markdown (GitHub 风格)"""
    r = subprocess.run(
        ["pandoc", "-f", "html", "-t", "gfm-raw_html", "--wrap=none"],
        input=html,
        text=True,
        capture_output=True,
    )
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or "pandoc 转换失败")
    return r.stdout


def download_resource(url, dest_dir, headers, content_type_hint=""):
    """下载页面里的图片/附件,返回相对路径"""
    dest_dir.mkdir(exist_ok=True)
    try:
        r = requests.get(unescape(url), headers=headers, timeout=60)
        r.raise_for_status()
    except Exception as e:
        print(f"    ⚠️  资源下载失败: {e}")
        return url
    ct = r.headers.get("Content-Type", "").lower()
    if not ct or "octet-stream" in ct:
        ct = content_type_hint.lower()
    ext = next((ext for kind, ext in {
        "jpeg": ".jpg", "jpg": ".jpg", "gif": ".gif", "png": ".png",
        "svg": ".svg", "pdf": ".pdf", "wordprocessingml": ".docx",
        "msword": ".doc", "spreadsheetml": ".xlsx", "ms-excel": ".xls",
        "presentationml": ".pptx", "powerpoint": ".ppt", "video/mp4": ".mp4",
        "audio/mpeg": ".mp3", "audio/mp4": ".m4a", "audio/wav": ".wav",
    }.items() if kind in ct), ".bin")
    fname = hashlib.md5(url.encode()).hexdigest()[:12] + ext
    for old_file in dest_dir.glob(f"{pathlib.Path(fname).stem}.*"):
        if old_file.name != fname:
            old_file.unlink()
    (dest_dir / fname).write_bytes(r.content)
    return f"attachments/{fname}"


def localize_resources(html, dest_dir, headers):
    """下载 Graph 返回的图片和 OneNote 文件附件。"""
    def image(match):
        tag = match.group(0)
        url = next((m.group(1) for pattern in [
            r'\bdata-fullres-src="([^"]+)"', r'\bsrc="([^"]+)"', r'\bdata-src="([^"]+)"',
        ] if (m := re.search(pattern, tag))), None)
        if not url or "graph.microsoft.com" not in url:
            return tag
        hint = next((m.group(1) for pattern in [
            r'\bdata-fullres-src-type="([^"]+)"', r'\bdata-src-type="([^"]+)"',
        ] if (m := re.search(pattern, tag))), "")
        path = download_resource(url, dest_dir, headers, hint)
        return re.sub(r'\b(src|data-fullres-src|data-src)="[^"]+"', lambda m: f'{m.group(1)}="{path}"', tag)

    def attachment(match):
        tag = match.group(0)
        url = re.search(r'\bdata="([^"]+)"', tag)
        name = re.search(r'\bdata-attachment="([^"]+)"', tag)
        if not url or not name or "graph.microsoft.com" not in url.group(1):
            return tag
        kind = re.search(r'\btype="([^"]+)"', tag)
        path = download_resource(url.group(1), dest_dir, headers, kind.group(1) if kind else "")
        return f'<a href="{path}">{name.group(1)}</a>'

    html = re.sub(r'<img\b[^>]*>', image, html, flags=re.I)
    return re.sub(r'<object\b[^>]*>', attachment, html, flags=re.I)


def preserve_onenote_formatting(html):
    """把 Graph HTML 中少量可映射的 OneNote 语义转为 Markdown 友好 HTML。"""
    def heading(match):
        style, body = match.group(1), match.group(2)
        size = re.search(r'font-size:(\d+(?:\.\d+)?)pt', style)
        if "font-weight:bold" not in style or not size:
            return match.group(0)
        level = "h1" if float(size.group(1)) >= 20 else "h2" if float(size.group(1)) >= 16 else None
        return f'<{level}>{body}</{level}>' if level else match.group(0)

    def styled_span(match):
        style, body = match.group(1), match.group(2)
        if "font-weight:bold" in style:
            return f'<strong>{body}</strong>'
        if "font-style:italic" in style:
            return f'<em>{body}</em>'
        if "background-color:" in style:
            return f'=={body}=='
        return match.group(0)

    def task(match):
        checked = "x" if match.group(1).endswith(":completed") else " "
        return f'<li>[{checked}] {match.group(2)}</li>'

    html = re.sub(r'<p\b[^>]*>\s*<span\b[^>]*style="([^"]*)"[^>]*>(.*?)</span>\s*</p>', heading, html, flags=re.I | re.S)
    html = re.sub(r'<span\b[^>]*style="([^"]*)"[^>]*>(.*?)</span>', styled_span, html, flags=re.I | re.S)
    return re.sub(r'<p\b[^>]*data-tag="(to-do(?::completed)?)"[^>]*>(.*?)</p>', task, html, flags=re.I | re.S)


# ─── 处理单个页面 ─────────────────────────────────────────────────
def existing_page(section_dir, page_id):
    """按 OneNote 页面 ID 找到上次迁移的文件,使重跑可恢复。"""
    marker = f"onenote_id: {page_id}"
    for path in section_dir.glob("*.md"):
        try:
            if marker in path.read_text(encoding="utf-8"):
                return path
        except OSError:
            pass


def process_page(page, section_dir, headers):
    pid = page["id"]
    title = sanitize(page.get("title") or "untitled")
    created = page["createdDateTime"]
    modified = page["lastModifiedDateTime"]

    try:
        html = gget(f"{BASE}/pages/{pid}/content", headers).text
    except Exception as e:
        print(f"  ⚠️  抓取失败 {title}: {e}")
        return None

    att = section_dir / "attachments"
    html = preserve_onenote_formatting(localize_resources(html, att, headers))

    try:
        md = html_to_md(html)
    except Exception as e:
        print(f"  ⚠️  转换失败 {title}: {e}")
        return None
    md = md.replace("- \\[ \\]", "- [ ]").replace("- \\[x\\]", "- [x]")
    fm = (
        f"---\n"
        f"title: {json.dumps(title, ensure_ascii=False)}\n"
        f"created: {created}\n"
        f"updated: {modified}\n"
        f"onenote_id: {pid}\n"
        f"---\n\n"
    )

    out = existing_page(section_dir, pid) or section_dir / f"{created[:10]} {title}.md"
    if not out.exists():
        n = 1
        while out.exists():
            n += 1
            out = section_dir / f"{created[:10]} {title} ({n}).md"
    out.write_text(fm + md, encoding="utf-8")
    set_file_times(out, created, modified)
    print(f"  ✅ {out.name}")
    return out


def list_sections(parent_url, headers):
    """获取分区及嵌套分区组中的分区。"""
    for section in list_all(f"{parent_url}/sections", headers):
        yield section
    for group in list_all(f"{parent_url}/sectionGroups", headers):
        yield from list_sections(f"{BASE}/sectionGroups/{group['id']}", headers)


# ─── 主流程 ───────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Migrate OneNote (cloud) to Obsidian markdown vault.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-o", "--output", required=True,
                        help="输出目录(通常是 Obsidian vault 里的一个子文件夹)")
    parser.add_argument("--tenant", default="consumers",
                        help="consumers=个人号(默认) / common=支持公司学校号")
    parser.add_argument("--client-id", default=DEFAULT_CLIENT_ID,
                        help="自定义 Azure App client_id(通常不用改)")
    parser.add_argument("--notebook",
                        help="只迁移名称包含该文字的笔记本(便于测试)")
    args = parser.parse_args()

    check_dependencies()

    vault = pathlib.Path(args.output).expanduser().resolve()
    vault.mkdir(parents=True, exist_ok=True)
    print(f"📚 输出目录: {vault}\n")

    token = device_login(args.client_id, args.tenant)
    headers = {"Authorization": f"Bearer {token}"}

    nbs = list_all(f"{BASE}/notebooks", headers)
    if args.notebook:
        nbs = [nb for nb in nbs if args.notebook.casefold() in nb["displayName"].casefold()]
        if not nbs:
            parser.error(f"未找到名称包含 {args.notebook!r} 的笔记本")
    print(f"找到 {len(nbs)} 个笔记本\n")

    migrated = failed = 0
    for nb in nbs:
        nb_dir = vault / sanitize(nb["displayName"])
        nb_dir.mkdir(exist_ok=True)
        print(f"📓 {nb['displayName']}")

        for sec in list_sections(f"{BASE}/notebooks/{nb['id']}", headers):
            sec_dir = nb_dir / sanitize(sec["displayName"])
            sec_dir.mkdir(exist_ok=True)
            print(f" 📂 {sec['displayName']}")

            for p in list_all(f"{BASE}/sections/{sec['id']}/pages?$top=100", headers):
                if process_page(p, sec_dir, headers):
                    migrated += 1
                else:
                    failed += 1

    print(f"\n🎉 完成,成功 {migrated} 页,失败 {failed} 页")
    print(f"📍 位置: {vault}")


if __name__ == "__main__":
    main()
