# OneNote to Obsidian

[English](README.md) | [日本語](README.ja.md)

一个将 OneNote 云端笔记导出为本地 Markdown 文件的轻量 Python 工具。输出适配 Obsidian，但工具不会直接导入、打开或修改 Obsidian 库。

## 能做什么

- 使用 Microsoft OAuth 设备码登录，只申请 `Notes.Read` 和 `offline_access`。
- 保留笔记本、分区、页面和嵌套分区组；页面以 Markdown 保存。
- 下载图片、PDF、Word、Excel、PowerPoint 和常见音视频附件到 `attachments/`。
- 将页面标题、粗体、斜体、高亮、待办、简单表格和链接尽量转换为 Obsidian 可用格式。
- 在 frontmatter、文件修改时间中保留原始时间；macOS 也会尝试恢复创建时间。
- 断点后可直接重跑：按 OneNote 页面 ID 更新已有页面，不重复创建文件。
- 对 Microsoft Graph 的限流、502/503/504 临时故障自动重试。

## 安装

需要 Python 3.8+、Pandoc 和 `requests`。

```bash
git clone https://github.com/YOUR_USERNAME/onenote-to-obsidian.git
cd onenote-to-obsidian
pip3 install -r requirements.txt

# macOS
brew install pandoc

# Ubuntu / Debian
sudo apt install pandoc
```

## 使用

先确认需要迁移的笔记本能在 <https://www.onenote.com/notebooks> 中看到，然后执行：

```bash
python3 onenote_to_obsidian.py --output ~/Documents/MyVault/OneNote
```

首次运行会显示 Microsoft 登录网址和一次性代码。授权后脚本自动继续；令牌仅保存在本机的 `~/.onenote_migrate_token.json`，并尝试设置为仅当前用户可读。

先小范围验证时：

```bash
python3 onenote_to_obsidian.py \
  --output ~/Documents/MyVault/OneNote \
  --notebook "测试笔记本"
```

参数：

| 参数 | 说明 |
| --- | --- |
| `-o, --output` | 必填，输出目录。建议先使用 Obsidian 库内的独立子目录。 |
| `--notebook` | 只迁移名称包含该文字的笔记本，适合验收和补跑。 |
| `--tenant` | `consumers` 为个人账号默认值；公司或学校账号可用 `common`。 |
| `--client-id` | 自定义 Azure App client ID；通常无需设置。 |

## 输出

```text
输出目录/
  笔记本/
    分区/
      2026-07-10 页面标题.md
      attachments/
        12ab34cd56ef.jpg
        90ab12cd34ef.pdf
```

每页带有 `title`、`created`、`updated` 和 `onenote_id` frontmatter。`onenote_id` 用于安全重跑和更新。

## 实测结果

项目已用真实 Microsoft 账户和真实 OneNote 页面测试：完整迁移 88 页，成功 88 页；包含 PDF、Word、图片、MP4 录音、表格、待办和格式的验收笔记本复测为 2 页成功、0 页失败。

测试同时发现并修复了：Graph 带小数秒时间戳的 macOS Python 兼容性、Graph 502/503/504 重试、OneNote `<object data-attachment>` 附件、无 MIME 响应的图片/音频扩展名，以及 Pandoc 转义待办框的问题。

## 工作原理

1. 通过 OAuth Device Code Flow 获取只读令牌。
2. 通过 Microsoft Graph 枚举笔记本、分区组、分区和页面。
3. 读取每页 HTML，下载 Graph 资源，并将附件链接替换为本地路径。
4. 将可识别的 OneNote HTML 语义转为 Markdown 友好格式，再由 Pandoc 转换。
5. 写入 frontmatter、设置时间戳，并根据 `onenote_id` 更新已有文件。

## 已知限制

- OneNote 是自由画布；浮动文本框、图片的位置会被拉平成线性文档。
- 字体、字号、文字颜色、背景、模板和网格线不能 1:1 迁移。红色文字会变成普通文字。
- 只有 Graph HTML 明确标记为标题、待办、附件或媒体的内容才能可靠识别。普通段落形式的“代码”“引用”无法安全推断。
- 复杂表格、合并单元格、手写笔迹、公式、页面密码、修订历史、OneNote 标签和内置录音元数据可能丢失或降级。
- 普通链接会保留；OneNote 内部链接不会自动变成 Obsidian 双向链接。
- 仅迁移已同步到 OneNote 云端、并且当前账号可通过 Graph 读取的内容。

迁移后请保留 OneNote 原稿，并对重要笔记抽样核对后再决定是否清理原始数据。

## 开发与验证

```bash
python3 -m unittest -v test_onenote_to_obsidian.py
```

测试不需要登录 Microsoft 账号，覆盖页面重跑、附件本地化、格式转换、时间戳兼容和临时 API 故障重试。

## 安全

- 工具不写入 OneNote；只请求 `Notes.Read`。
- 令牌不会写入项目目录，也被 `.gitignore` 排除。
- 如需撤销授权，可在 Microsoft 帐户授权管理页操作。

## License

[MIT](LICENSE)
