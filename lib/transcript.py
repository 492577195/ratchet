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
import shlex
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
    context_window: int = 0      # 显式配置、Codex transcript 实测值，或保守兜底
    turns: int = 0               # assistant 轮数
    unrecognized: bool = False   # 文件非空，但没有一条记录属于已知 transcript schema

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read + self.cache_write

    @property
    def context_pct(self) -> float:
        if not self.context_window:
            return 0.0
        return round(self.context_used * 100.0 / self.context_window, 1)


# Claude Code transcript 不带窗口：model 只有 "claude-opus-4-8" 这样的名字，同一名字
# 可能跑在 200k 或 1M 上（实测确认），所以应由 .ratchet/config.json 显式提供。
# Codex 当前会在 token_count 里给 model_context_window；没有显式配置时直接采用实测值。
# 两边都拿不到时才走下面的自动升档兜底 —— 宁可高估，也绝不能再输出
# "ctx 156%" 这种荒谬数字（首版就是这么错的）。
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


_CODEX_RECORD_TYPES = {"session_meta", "turn_context", "world_state", "event_msg", "response_item"}


def _as_int(value: Any) -> int:
    """外部 transcript 的计数值必须容错；坏字段按 0，不让 SessionEnd 崩掉。"""
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _append_unique(items: list[str], value: Any) -> None:
    if isinstance(value, str) and value and value not in items:
        items.append(value)


def _codex_command(value: Any) -> str:
    """Codex CommandExecution.command 是 argv；shell -lc 时日志只留实际脚本。"""
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, list) or not all(isinstance(part, str) for part in value):
        return ""
    if (len(value) >= 3 and os.path.basename(value[0]) in {"sh", "bash", "zsh"}
            and value[1] in {"-c", "-lc"}):
        return value[2].strip()
    return shlex.join(value).strip()


def _parse_codex_item(d: Digest, item: Any) -> bool:
    """解析 event_msg.item_completed 的当前 Codex 结构。返回是否为 agent 消息。"""
    if not isinstance(item, dict):
        return False
    kind = item.get("type")
    if kind == "AgentMessage":
        return True
    if kind == "CommandExecution":
        d.tools["Bash"] += 1
        cmd = _codex_command(item.get("command"))
        if cmd:
            d.commands.append(cmd)
    elif kind == "FileChange":
        d.tools["apply_patch"] += 1
        changes = item.get("changes")
        if isinstance(changes, dict):
            for path, change in changes.items():
                _append_unique(d.files_written, path)
                if isinstance(change, dict):
                    _append_unique(d.files_written, change.get("move_path"))
    elif kind == "McpToolCall":
        server = str(item.get("server") or "mcp")
        tool = str(item.get("tool") or "unknown")
        d.tools[f"{server}:{tool}"] += 1
    elif kind == "Extension":
        d.tools[str(item.get("kind") or "Extension")] += 1
    return False


def _apply_codex_usage(d: Digest, info: Any) -> int:
    """应用最新 token_count 快照，返回平台给出的真实上下文窗口。"""
    if not isinstance(info, dict):
        return 0
    total = info.get("total_token_usage")
    if isinstance(total, dict):
        # Codex 的 input_tokens 已包含两类缓存输入；拆开后再交给 Digest，避免总量双计。
        input_total = _as_int(total.get("input_tokens"))
        cached = _as_int(total.get("cached_input_tokens") or total.get("cache_read_input_tokens"))
        cache_write = _as_int(total.get("cache_write_input_tokens"))
        d.input_tokens = max(input_total - cached - cache_write, 0)
        d.output_tokens = _as_int(total.get("output_tokens"))
        d.cache_read = cached
        d.cache_write = cache_write

    last = info.get("last_token_usage")
    if isinstance(last, dict):
        # last.input_tokens 同样已含缓存，正好就是这一轮真实上下文输入量。
        d.context_used = _as_int(last.get("input_tokens"))
    return _as_int(info.get("model_context_window"))


def parse(path: str, context_window: int | None = None) -> Digest:
    """解析 transcript JSONL。容错优先：坏行跳过，绝不因一行畸形而让 hook 崩掉。

    context_window: 显式配置，优先于 Codex transcript 实测值；两者都无时走兜底。
    """
    d = Digest()
    if not path or not os.path.isfile(path):
        return d

    model = ""
    last_usage: dict[str, Any] | None = None
    codex_window = 0
    codex_agent_turns = 0
    nonempty_lines = 0
    known_records = 0

    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            nonempty_lines += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # 坏行跳过
            if not isinstance(rec, dict):
                continue

            record_type = rec.get("type")
            if record_type in {"assistant", "user"}:
                known_records += 1
            if record_type == "assistant":
                d.turns += 1

                msg = rec.get("message") or {}
                if not isinstance(msg, dict):
                    msg = {}
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
                    if not isinstance(inp, dict):
                        inp = {}
                    d.tools[name] += 1

                    if name in ("Write", "Edit", "NotebookEdit"):
                        fp = inp.get("file_path") or inp.get("notebook_path")
                        _append_unique(d.files_written, fp)
                    elif name == "Read":
                        _append_unique(d.files_read, inp.get("file_path"))
                    elif name == "Bash":
                        cmd = (inp.get("command") or "").strip()
                        if cmd:
                            d.commands.append(cmd)
                continue

            if record_type not in _CODEX_RECORD_TYPES:
                continue
            known_records += 1
            payload = rec.get("payload")
            if not isinstance(payload, dict):
                continue

            if record_type == "turn_context":
                model = payload.get("model") or model
            elif record_type == "response_item":
                if payload.get("type") == "message" and payload.get("role") == "assistant":
                    d.turns += 1
            elif record_type == "event_msg":
                event_type = payload.get("type")
                if event_type == "token_count":
                    codex_window = _apply_codex_usage(d, payload.get("info")) or codex_window
                elif event_type == "item_completed":
                    codex_agent_turns += int(_parse_codex_item(d, payload.get("item")))

    if not d.turns and codex_agent_turns:
        d.turns = codex_agent_turns
    d.unrecognized = nonempty_lines > 0 and known_records == 0

    # 上下文占用 = 最后一轮真实喂进模型的量（输入 + 两类缓存），不是累加值。
    if last_usage:
        d.context_used = (
            (last_usage.get("input_tokens") or 0)
            + (last_usage.get("cache_read_input_tokens") or 0)
            + (last_usage.get("cache_creation_input_tokens") or 0)
        )
    detected_window = context_window or codex_window or None
    d.context_window = _resolve_window(model, d.context_used, detected_window)
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
