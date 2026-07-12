"""
transcript.py — 会话 transcript(JSONL) 的共享解析器。

Claude Code 与 Codex 的 hook 都在 stdin payload 里给 `transcript_path`（P0 实测确认，
两边字段名一致），指向一份 append-only 的 JSONL 会话记录。

这一个数据源同时喂两个消费方，所以解析逻辑只写一遍：
  - ratchet-context : 上下文占用率（喂 statusLine）—— 取代「让模型自己估算并汇报」
  - ratchet-digest  : session 日志的机械部分 —— 取代「让模型手写 8 段」

设计依据（P0 实测）：statusLine 的 stdin 并不直接提供上下文占比，它只给 transcript_path，
占比要自己算。ccstatusline 等工具正是这么做的。
"""
from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Digest:
    """一次会话的机械事实。全部可从 transcript 推出，无需模型参与。"""

    tools: Counter = field(default_factory=Counter)      # 工具名 -> 调用次数
    files_written: list[str] = field(default_factory=list)
    files_read: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)    # 执行过的 bash 命令
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    context_used: int = 0        # 最后一轮的上下文占用（= in + cache_read + cache_write）
    context_window: int = 0      # 上下文窗口大小（从 transcript 推断，未知则 0）
    turns: int = 0               # assistant 轮数

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read + self.cache_write

    @property
    def context_pct(self) -> float:
        if not self.context_window:
            return 0.0
        return round(self.context_used * 100.0 / self.context_window, 1)


# 上下文窗口不在 transcript 里 —— model 字段只有 "claude-opus-4-8" 这样的名字，
# 不带 [1M] 之类的档位标记（实测确认）。同一个模型名可能跑在 200k 或 1M 上。
# 所以窗口大小是**环境属性**，必须由 .ratchet/config.json 显式提供。
# 下面的推断只是没有配置时的兜底，且带自动升档保护 —— 宁可高估，
# 也绝不能再输出 "ctx 156%" 这种荒谬数字（首版就是这么错的）。
_FALLBACK = 200_000
_LADDER = [200_000, 400_000, 1_000_000, 2_000_000]


def _resolve_window(model: str, used: int, configured: int | None) -> int:
    if configured:
        return configured
    w = _FALLBACK
    # 兜底保护：实际用量已经超过猜测窗口 → 沿档位阶梯上调，直到装得下。
    for step in _LADDER:
        if used <= step:
            w = step
            break
    else:
        w = _LADDER[-1]
    return max(w, _FALLBACK)


def parse(path: str, context_window: int | None = None) -> Digest:
    """解析 transcript JSONL。容错优先：坏行跳过，绝不因一行畸形而让 hook 崩掉。

    context_window: 由 .ratchet/config.json 提供。None 时走兜底推断。
    """
    d = Digest()
    if not path or not os.path.isfile(path):
        return d

    model = ""
    last_usage: dict[str, Any] | None = None

    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # 坏行跳过

            if rec.get("type") != "assistant":
                continue
            d.turns += 1

            msg = rec.get("message") or {}
            model = msg.get("model") or model

            usage = msg.get("usage")
            if isinstance(usage, dict):
                last_usage = usage
                d.input_tokens += usage.get("input_tokens", 0) or 0
                d.output_tokens += usage.get("output_tokens", 0) or 0
                d.cache_read += usage.get("cache_read_input_tokens", 0) or 0
                d.cache_write += usage.get("cache_creation_input_tokens", 0) or 0

            for blk in msg.get("content") or []:
                if not isinstance(blk, dict) or blk.get("type") != "tool_use":
                    continue
                name = blk.get("name", "?")
                inp = blk.get("input") or {}
                d.tools[name] += 1

                if name in ("Write", "Edit", "NotebookEdit"):
                    fp = inp.get("file_path") or inp.get("notebook_path")
                    if fp and fp not in d.files_written:
                        d.files_written.append(fp)
                elif name == "Read":
                    fp = inp.get("file_path")
                    if fp and fp not in d.files_read:
                        d.files_read.append(fp)
                elif name == "Bash":
                    cmd = (inp.get("command") or "").strip()
                    if cmd:
                        d.commands.append(cmd)

    # 上下文占用 = 最后一轮真实喂进模型的量（输入 + 两类缓存），不是累加值。
    if last_usage:
        d.context_used = (
            (last_usage.get("input_tokens") or 0)
            + (last_usage.get("cache_read_input_tokens") or 0)
            + (last_usage.get("cache_creation_input_tokens") or 0)
        )
    d.context_window = _resolve_window(model, d.context_used, context_window)
    return d


def load_config(root: str | None = None) -> dict:
    """读 .ratchet/config.json。缺失返回空 dict —— 配置缺失不该让 hook 崩。"""
    root = root or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    p = os.path.join(root, ".ratchet", "config.json")
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def from_hook_stdin(payload: dict, root: str | None = None) -> Digest:
    """hook 的 stdin payload -> Digest。CC 与 Codex 都用 transcript_path 这个键（P0 实测）。"""
    cfg = load_config(root)
    return parse(payload.get("transcript_path", ""), cfg.get("context_window"))
