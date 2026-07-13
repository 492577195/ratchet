# 参与 ratchet

先读这一节，能省掉一次白干。

## 什么样的改动会被拒绝

这个项目有一条贯穿始终的立场：**能机器化的纪律，不许写成文字规则。** 所以下面这些改动，无论写得多好都会被拒：

| 改动 | 为什么拒 |
|---|---|
| 「在宪法里加一条规则来防止 X」 | 先问：X 能不能写成校验器？**能，就去写校验器。** 规则是校验器写不出来时的退路，不是首选 |
| 让热区（每次进上下文的文件）变大 | 热区必须与项目年龄无关。这是本项目存在的理由，不接受「就加这一点点」 |
| 修了 bug 但没加测试 | 每个真实发生过的 bug 都必须在 `test/run.sh` 里留下一条**永远拦住它的断言**。不写「下次注意」，写测试 |
| 给 `bin/` 引入外部依赖 | `bin/` 下必须是平台无关、零外部依赖的确定性脚本。这是 CC / Codex / CI 三处复用的支点 |
| 凭印象写的 schema / API 字段名 | 配置 schema、框架 API、协议字段，必须有 URL 可追溯的现行文档佐证。模型会编字段名 |

## 机器会自动拒绝的

以下四条不靠 review，`pre-push` 和 CI 会直接拦（`.githooks/pre-push` + `.github/workflows/test.yml`）：

1. **测试不过** —— `./test/run.sh` 必须全绿（当前 91 PASS / 0 FAIL ✅）
2. **版本号三处不一致** —— `VERSION`、`.claude-plugin/plugin.json`、`.codex-plugin/plugin.json` 必须相同
3. **`hooks/hooks.json` 顶层出现 `description` / `hooks` 以外的键** —— Codex 会拒绝整个文件并**静默丢弃全部 hook**。这是真实发生过的线上故障 ⚠️
4. **`templates/constitution.md` 超过 4,096 B** —— 宪法硬上限。想加一条，**先删一条**

> `pre-push` 可以被 `--no-verify` 绕过，CI 绕不过。别绕。

## 上手

```bash
git clone git@github.com:492577195/ratchet.git
cd ratchet
git config core.hooksPath .githooks   # 装上 pre-push 门禁，必做
./test/run.sh                          # 应该全绿
```

**本地开发插件**：用 `--plugin-dir` 指向仓库绝对路径，in-place 加载，不污染你已安装的版本。

分支：`main` 正式版（用户装这个，永远绿）· `dev` 日常开发。**PR 提到 `dev`**，不要直接提 `main`。

## 提改动之前

- **拆小。** 一个 PR 只做一件事。几百行混着改的 PR 会被要求拆开重来
- **不确定就先开 issue 问**，别闷头写完再来对齐方案
- 改了行为 → 同步改 README；改了纪律 → 同步改 `templates/constitution.md`（注意 4 KB 上限）
- 提交前跑一遍 `./test/run.sh` 和 `bin/ratchet-overhead`（后者体检热区有没有被你撑大）

## 报 bug

用 [issue 模板](https://github.com/492577195/ratchet/issues/new/choose)。请务必带上：

- 你用的是 **Claude Code 还是 Codex**（两个平台的 hook 行为不同，这是最关键的一条信息）
- `cat VERSION` 的输出
- 触发它的最小复现步骤

如果是「AI 又干了不该干的事」这类问题 —— 那正是本项目要解决的。请在 issue 里说清楚**它做了什么**、**你希望哪个校验器拦住它**。这类 issue 最有价值，因为它直接变成下一条断言。
