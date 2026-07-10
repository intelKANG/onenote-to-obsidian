import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


sys.modules.setdefault("requests", types.SimpleNamespace(get=None, post=None))
import onenote_to_obsidian as app


class Response:
    def __init__(self, text="", content=b"", headers=None, status_code=200):
        self.text = text
        self.content = content
        self.headers = headers or {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class ProcessPageTest(unittest.TestCase):
    page = {
        "id": "page-1",
        "title": "测试页面",
        "createdDateTime": "2024-05-10T08:30:00Z",
        "lastModifiedDateTime": "2024-05-12T14:22:33Z",
    }

    def test_page_is_localized_and_updated_on_rerun(self):
        html = '<p>第一版</p><img src="https://graph.microsoft.com/resource/1">'
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(app, "gget", return_value=Response(text=html)), \
             patch.object(app, "html_to_md", side_effect=lambda value: value), \
             patch.object(app, "set_file_times"), \
             patch.object(app.requests, "get", return_value=Response(content=b"png", headers={"Content-Type": "image/png"})):
            section = Path(tmp)
            first = app.process_page(self.page, section, {})
            second = app.process_page(self.page, section, {})

            self.assertEqual(first, second)
            self.assertEqual(len(list(section.glob("*.md"))), 1)
            self.assertIn('src="attachments/', first.read_text(encoding="utf-8"))
            self.assertEqual(len(list((section / "attachments").iterdir())), 1)

    def test_failed_page_is_not_counted_as_success(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(app, "gget", side_effect=RuntimeError("offline")):
            self.assertIsNone(app.process_page(self.page, Path(tmp), {}))

    def test_graph_fractional_timestamp_is_accepted(self):
        with patch.object(app.os, "utime") as set_time, patch.object(app, "IS_MAC", False):
            app.set_file_times(Path("note.md"), "2021-01-12T18:28:13.16+00:00", "2021-01-12T18:28:13.16+00:00")
        set_time.assert_called_once()

    def test_temporary_graph_failure_is_retried(self):
        with patch.object(app.requests, "get", side_effect=[Response(status_code=503), Response(text="ok")]), \
             patch.object(app.time, "sleep") as sleep:
            self.assertEqual(app.gget("https://example.test", {}).text, "ok")
        sleep.assert_called_once_with(5)

    def test_graph_attachments_and_formatting_are_preserved(self):
        html = '''<object data-attachment="manual.pdf" type="application/pdf" data="https://graph.microsoft.com/pdf" />
        <img src="https://graph.microsoft.com/image" data-src-type="image/jpeg" />
        <p><span style="font-size:24pt;font-weight:bold">标题</span></p>
        <p><span style="font-weight:bold">加粗</span> <span style="font-style:italic">斜体</span></p>
        <p data-tag="to-do:completed">完成</p>'''
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(app, "gget", return_value=Response(text=html)), \
             patch.object(app, "html_to_md", side_effect=lambda value: value), \
             patch.object(app, "set_file_times"), \
             patch.object(app.requests, "get", return_value=Response(content=b"file", headers={})):
            result = app.process_page(self.page, Path(tmp), {})
            result_text = result.read_text(encoding="utf-8")
            self.assertIn('<a href="attachments/', result_text)
            self.assertIn('.jpg', result_text)
            self.assertIn('<h1>标题</h1>', result_text)
            self.assertIn('<strong>加粗</strong>', result_text)
            self.assertIn('<em>斜体</em>', result_text)
            self.assertIn('<li>[x] 完成</li>', result_text)
            self.assertEqual(len(list((Path(tmp) / "attachments").iterdir())), 2)

    def test_resource_type_update_replaces_old_extension(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(app.requests, "get", return_value=Response(content=b"file", headers={})):
            folder = Path(tmp)
            app.download_resource("https://graph.microsoft.com/resource", folder, {}, "")
            app.download_resource("https://graph.microsoft.com/resource", folder, {}, "image/jpeg")
            self.assertEqual([path.suffix for path in folder.iterdir()], [".jpg"])

    def test_escaped_checkbox_becomes_obsidian_task(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(app, "gget", return_value=Response(text="<p>任务</p>")), \
             patch.object(app, "html_to_md", return_value="- \\[ \\] 未完成\n- \\[x\\] 已完成"), \
             patch.object(app, "set_file_times"):
            result = app.process_page(self.page, Path(tmp), {})
            result_text = result.read_text(encoding="utf-8")
        self.assertIn("- [ ] 未完成", result_text)
        self.assertIn("- [x] 已完成", result_text)


if __name__ == "__main__":
    unittest.main()
