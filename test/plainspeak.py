#!/usr/bin/env python3
"""所有 hook 调用均在临时项目运行，不写仓库的运行时数据。"""

import datetime
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "bin/ratchet-plainspeak"


def assistant(text):
    return {"type": "assistant", "message": {"content": [
        {"type": "thinking", "thinking": "结论 HIDDEN hidden.py"},
        {"type": "tool_use", "name": "Bash", "input": {"command": "TOOL"}},
        {"type": "text", "text": text},
    ]}}


class PlainspeakTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ratchet-plainspeak-")
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.transcript = self.project / "transcript.jsonl"
        self.hits = self.project / ".ratchet/hits.jsonl"
        self.payload = {"cwd": str(self.project), "transcript_path": str(self.transcript),
                        "session_id": "session123456"}

    def write(self, *records):
        self.transcript.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                           for r in records), encoding="utf-8")

    def invoke(self, raw=None):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project), PYTHONDONTWRITEBYTECODE="1")
        started = time.perf_counter()
        result = subprocess.run([str(HOOK)], input=json.dumps(self.payload) if raw is None else raw,
                                text=True, capture_output=True, cwd=self.project, env=env, timeout=3)
        self.elapsed = (time.perf_counter() - started) * 1000
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "{}\n", ""))
        self.assertFalse((self.project / ".ratchet/state.json").exists())
        return [json.loads(line) for line in self.hits.read_text().splitlines()] if self.hits.exists() else []

    def test_plainspeak_fields_append_and_last_body(self):
        text = "结论：本轮已完成。"
        self.write(assistant("old.py"), assistant(text), {"type": "user", "message": "忽略"})
        self.hits.parent.mkdir()
        self.hits.write_text('{"existing":true}\n')
        rows = self.invoke()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], {"existing": True})
        record = rows[1]
        self.assertEqual(set(record), {"rule", "decision", "at", "chars", "idents", "lead", "sid"})
        self.assertEqual(record, dict(record, rule="plainspeak", decision="observe",
                                     chars=len(text), idents=0, lead="conclusion", sid="session1"))
        self.assertIsNotNone(datetime.datetime.fromisoformat(record["at"]).tzinfo)

    def test_plainspeak_missing_transcript(self):
        self.assertEqual(self.invoke(), [])
        self.assertFalse(self.hits.exists())

    def test_plainspeak_bad_json_encoding_and_payload(self):
        for data in (b"broken json\n", b"\xff\xfe\n", b"[]\nnull\n", b""):
            with self.subTest(data=data):
                self.transcript.write_bytes(data)
                self.assertEqual(self.invoke(), [])
        for raw in ("not json", "[]", "null", "{}"):
            with self.subTest(payload=raw):
                self.assertEqual(self.invoke(raw), [])

    def test_plainspeak_lead_and_200_character_boundary(self):
        for text, expected in (("结论：继续", "conclusion"), ("parser.py 的字段说明", "detail"),
                               ("", "unknown"), ("字" * 200 + "结论", "detail"),
                               ("字" * 198 + "结论", "conclusion")):
            with self.subTest(text=text):
                self.write(assistant(text))
                self.assertEqual(self.invoke()[-1]["lead"], expected)

    def test_plainspeak_idents_four_patterns_and_overlap(self):
        self.write(assistant("`token` app.py /tmp/example CONFIG"))
        self.assertEqual(self.invoke()[-1]["idents"], 4)
        self.write(assistant("`/tmp/app.py`"))
        self.assertEqual(self.invoke()[-1]["idents"], 3)

    def test_plainspeak_codex_excludes_analysis_and_tools(self):
        self.write(assistant("旧正文"), {"type": "response_item", "payload": {
            "type": "message", "role": "assistant", "channel": "final",
            "content": [{"type": "output_text", "text": "结论：成功"}],
        }}, {"type": "response_item", "payload": {
            "type": "message", "role": "assistant", "channel": "analysis",
            "content": [{"type": "output_text", "text": "HIDDEN hidden.py"}],
        }}, {"type": "response_item", "payload": {"type": "function_call"}})
        row = self.invoke()[0]
        self.assertEqual((row["chars"], row["idents"], row["lead"]), (5, 0, "conclusion"))

    def test_plainspeak_tail_limit_and_performance(self):
        # 超长历史行及窗口边界的半个 UTF-8 字符不影响最后一条完整消息。
        prefix = json.dumps(assistant("旧" * 200000), ensure_ascii=False).encode("utf-8")
        last = json.dumps(assistant("结论：成功"), ensure_ascii=False).encode("utf-8")
        self.transcript.write_bytes(prefix + b"\n" + last + b"\n")
        self.assertEqual(self.invoke()[0]["chars"], 5)
        print("plainspeak 大文件端到端耗时：{:.1f} ms".format(self.elapsed), flush=True)
        self.assertLess(self.elapsed, 300)
        # 正文在窗口之外时，不得回头全文扫描、记录旧消息。
        self.transcript.write_bytes(last + b"\n" + b" " * (256 * 1024))
        self.assertEqual(len(self.invoke()), 1)

        namespace = runpy.run_path(str(HOOK))
        class BoundedReader(io.BytesIO):
            consumed = 0

            def read(stream, count=-1):
                self.assertGreaterEqual(count, 0)
                stream.consumed += count
                self.assertLessEqual(stream.consumed, 256 * 1024)
                return super().read(count)

        with patch("builtins.open", return_value=BoundedReader(prefix + b"\n" + last)):
            self.assertEqual(namespace["last_body"]("fixture"), "结论：成功")

    def test_plainspeak_permission_error_and_directory_conflict(self):
        self.write(assistant("结论"))
        self.hits.parent.write_text("被文件占用")
        self.assertEqual(self.invoke(), [])
        # 用确定性故障注入覆盖权限异常，不依赖运行测试的用户是否有 root 权限。
        namespace = runpy.run_path(str(HOOK))
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(self.payload))), patch("sys.stdout", output), \
                patch("builtins.open", side_effect=PermissionError("denied")):
            self.assertEqual(namespace["main"](), 0)
        self.assertEqual(output.getvalue(), "{}\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
