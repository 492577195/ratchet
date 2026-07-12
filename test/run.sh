#!/usr/bin/env bash
# ratchet 回归测试。
#
# 棘轮原则：每个真实发生过的 bug，都必须在这里留下一条永远拦住它的断言。
# 不写「下次注意」，写测试。
set -u
cd "$(dirname "$0")/.." || exit 1
BIN=./bin
PASS=0; FAIL=0
ok()   { printf "  ✅ %s\n" "$1"; PASS=$((PASS+1)); }
bad()  { printf "  ❌ %s\n     %s\n" "$1" "${2:-}"; FAIL=$((FAIL+1)); }

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

# ─────────────────────────────────────────────────────────────
echo "K1 · 起手简报字节预算（≤ 2048 B，与项目年龄无关）"
# ─────────────────────────────────────────────────────────────
python3 - "$TMP/worst.json" <<'PY'
import json, sys
z = lambda n: "阻" * n          # 中文 3 B/char —— 最坏情况
json.dump({
  "schema_version": 1, "preset": "complex",
  "current": {"task": z(50), "next": z(50), "iteration": "v10.20.30-rc1", "stage": "implementation"},
  "blocked": [{"what": z(35), "unblock": z(35), "since": "2026-07-12"} for _ in range(2)],
  "pending_user": [{"question": z(45), "raised": "2026-07-12"} for _ in range(2)],
  "recent_decisions": [{"decision": z(30), "why": z(25), "date": "2026-07-12"} for _ in range(3)],
  "session": {"last": 99999, "last_date": "2026-07-12", "log_written": False},
  "updated_at": "2026-07-12T09:00:00Z",
}, open(sys.argv[1], "w"), ensure_ascii=False)
PY
# 每个字段都顶到 schema 上限时仍须过预算 —— 这是 K1/K4 的结构性保证，不是「但愿」
if out=$($BIN/ratchet-brief --state "$TMP/worst.json" --check 2>&1); then
  ok "最坏情况过预算 ($out)"
else
  bad "最坏情况超预算" "$out"
fi

# 回归 · schema 首版把上限定宽了，最坏情况实测 3751 B、超标 83%。
# 这条断言锁住「上限必须由 K1 预算反推」这件事。
n=$($BIN/ratchet-brief --state "$TMP/worst.json" 2>/dev/null | wc -c | tr -d ' ')
[ "$n" -le 2048 ] && ok "最坏渲染 ${n} B ≤ 2048 B" || bad "最坏渲染 ${n} B > 2048 B"

# ─────────────────────────────────────────────────────────────
echo
echo "REGRESSION · 上下文占比不得出现 >100% 的荒谬值"
# ─────────────────────────────────────────────────────────────
# 真实 bug：靠模型名猜窗口，把跑在 1M 上的会话按 200k 算，输出 "ctx 156%"。
# 根因：transcript 里根本没有窗口信息（实测确认），它是环境属性，必须显式配置。
# 兜底路径必须自动升档，绝不能再吐出 >100%。
python3 - "$TMP/big.jsonl" <<'PY'
import json, sys
with open(sys.argv[1], "w") as f:
    f.write(json.dumps({"type": "assistant", "message": {
        "model": "claude-opus-4-8", "usage": {
            "input_tokens": 2, "output_tokens": 100,
            "cache_read_input_tokens": 310_000, "cache_creation_input_tokens": 900},
        "content": []}}) + "\n")
PY
line=$($BIN/ratchet-context --transcript "$TMP/big.jsonl")
pct=$(printf '%s' "$line" | sed -E 's/.*ctx ([0-9]+)%.*/\1/')
if [ -n "$pct" ] && [ "$pct" -le 100 ]; then
  ok "无配置时兜底升档，占比 ${pct}% ≤ 100% ($line)"
else
  bad "占比 >100%（首版 bug 复发）" "$line"
fi
# 显式配置窗口时必须如实采用
line=$($BIN/ratchet-context --transcript "$TMP/big.jsonl" --window 1000000)
echo "$line" | grep -q "1000k" && ok "显式 --window 生效 ($line)" || bad "显式 --window 未生效" "$line"

# ─────────────────────────────────────────────────────────────
echo
echo "REGRESSION · session 日志不得把变量赋值当成「关键命令」"
# ─────────────────────────────────────────────────────────────
# 真实 bug：取多行脚本的第一行，抽出来全是 TDIR=... / set -u，而非真正执行的命令。
python3 - "$TMP/cmd.jsonl" <<'PY'
import json, sys
script = 'set -u\nTDIR="$HOME/x"\nSP=/tmp/y\ncodex plugin list --json\n'
with open(sys.argv[1], "w") as f:
    f.write(json.dumps({"type": "assistant", "message": {
        "model": "claude-opus-4-8", "usage": {},
        "content": [{"type": "tool_use", "name": "Bash", "input": {"command": script}}]}}) + "\n")
PY
body=$($BIN/ratchet-digest --transcript "$TMP/cmd.jsonl" --session 1)
echo "$body" | grep -q 'codex plugin list' && ok "抽到实质命令 (codex plugin list)" || bad "未抽到实质命令"
if echo "$body" | grep -qE '^(TDIR=|SP=|set -u)'; then
  bad "把变量赋值/set 当成命令（首版 bug 复发）"
else
  ok "变量赋值与 set 选项已被剔除"
fi

# ─────────────────────────────────────────────────────────────
echo
echo "ROBUSTNESS · 坏输入绝不能让 hook 崩掉"
# ─────────────────────────────────────────────────────────────
printf 'not json\n{"type":"assistant"}\n' > "$TMP/bad.jsonl"
$BIN/ratchet-context --transcript "$TMP/bad.jsonl" >/dev/null 2>&1 && ok "畸形 transcript 不崩" || bad "畸形 transcript 导致非零退出"
$BIN/ratchet-context --transcript /nonexistent >/dev/null 2>&1 && ok "transcript 缺失不崩" || bad "transcript 缺失导致非零退出"
echo '{}' > "$TMP/empty.json"
$BIN/ratchet-brief --state "$TMP/empty.json" >/dev/null 2>&1
[ $? -le 1 ] && ok "空 state 优雅降级" || bad "空 state 处理异常"

echo
echo "──────────────────────────────"
printf "PASS %d   FAIL %d\n" "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
