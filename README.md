# ratchet

AI 协作工程脚手架。跨 Claude Code 与 OpenAI Codex。

两件事，一句话说完：

1. **能机器化的工程纪律，一律下沉为确定性门禁。** 写在 CLAUDE.md 里靠模型自觉遵守的规则会退化 —— 而修复方式往往是「再加一条规则」，于是规则膨胀、上下文稀释、更容易被忽略、再加规则。
2. **机制自身的上下文成本必须与项目年龄无关。** 否则跑上一年，起手仪式就会吃掉本该属于任务的上下文。

---

## 为什么

这套东西是从一个真实工程里抽出来的 —— 那个工程用两个月、251 个会话，长出了一套完整的 AI 协作方法论，也长出了它的病。实测账单：

| | |
|---|---|
| 每次会话「起手必读」文件合计 | **247,366 B**（约 8–10 万 token） |
| 其中 `PLAN/current.md` 单文件 | **164,297 B**，且仍在增长 |
| 230 份 session 日志 | 1.86 MB |
| `CLAUDE.md` + `AGENTS.md` | 25 KB，每次会话全量进上下文 |
| 校验脚本 | 31 KB 的正则怪物，检查项从 ① 叠到 ⑪ |

**一个会话还没开始干活，起手仪式就吞掉近 10 万 token。** 而这条曲线是发散的。

更根本的问题：那 164 KB 里，真正「每次都需要」的决策信息只有 **4,311 B**。剩下 96% 是没人敢删的历史 —— 它们不是信息，是沉积物。

## 怎么治

**状态与叙述分离。**

- **状态**（在做什么 / 下一步 / 阻塞 / 待拍板 / 最近决策）→ `.ratchet/state.json`，机器读写，schema 校验
- **叙述**（日志 / 修订 / 复盘）→ Markdown，人和 AI 读，机器不解析
- **起手简报** → 由 state 自动渲染，**硬上限 2 KB，禁止手工编辑** —— 它不会过期，所以那 31 KB 正则脚本的大半检查项不是被修好，是不再需要存在

**冷热分离。** 热区（每次进上下文）必须恒定；冷区（归档）随便长。冷区膨胀无所谓，热区膨胀才是病。

**棘轮 + 棘爪。** 每次失败转化为永久物理约束（`/ratchet`）—— 但棘轮只进不退，是熵增引擎，所以必须配套减法（`/slim`）：规则带命中计数，长期零命中的淘汰，高频命中的升级成硬校验器。

## 效果

| | 原工程 | ratchet |
|---|---|---|
| 起手注入 | 247,366 B（发散 📈） | **最坏 1,834 B / 真实 575 B**（恒定） |
| 收尾模型手写 | 8 段 ≈ 8 KB | **≤ 1 KB**，其余机器生成 |
| 与项目年龄的关系 | 线性增长 | **无关**（schema 上限 + 冷热分离结构性保证） |

最坏情况的 1,834 B 不是「但愿如此」—— schema 的 `maxItems` / `maxLength` 在数学上保证渲染永远超不过它。装不下的东西会被机器拒绝，而不是靠人记得清理。

---

## 装

本仓是**私有仓**，所以必须用 SSH URL —— `492577195/ratchet` 这种简写会走匿名 HTTPS，被 GitHub 拒绝。（若日后改为公开仓，简写才能用。）

**Claude Code**

```
/plugin marketplace add git@github.com:492577195/ratchet.git
/plugin install ratchet@ratchet
```

**Codex**

```bash
codex plugin marketplace add git@github.com:492577195/ratchet.git
codex plugin add ratchet@ratchet
```

本地开发时把 URL 换成仓库绝对路径即可。

装完在项目里跑 `/ratchet:init`。**注意 Codex 没有自定义 slash 命令**，靠 skill 的 description 自然语言触发 —— 直接说「初始化这个项目的工程脚手架」。

选档位（普通 / 复杂），铺出 `.ratchet/`。

**简单项目不要装** —— 这是最有效的防臃肿措施。

### 上下文常显（可选）

`ratchet-context` 可以喂 statusLine，把「上下文卫生」从「让模型自己估算并汇报」变成常显。**不默认开启**（会覆盖你现有的状态栏配置）。要用的话，在 `~/.claude/settings.json` 加：

```json
{ "statusLine": { "type": "command", "command": "<plugin-root>/bin/ratchet-context" } }
```

Codex 侧内置支持，`~/.codex/config.toml`：

```toml
[tui]
status_line = ["model", "directory", "context-percent"]
```

---

## 组件

```
bin/ratchet-init       铺脚手架到项目（确定性、幂等、永不覆写你的数据）
bin/ratchet-brief      起手简报（state.json → ≤2 KB，SessionStart 注入）
bin/ratchet-guard      危险动作拦截（PreToolUse）+ Slopsquatting 防护
bin/ratchet-state      schema 校验（PostToolUse）—— K1/K4 的执行者
bin/ratchet-digest     收尾自动留痕（SessionEnd）
bin/ratchet-context    上下文占比（statusLine）
bin/ratchet-overhead   机制税审计 —— 给脚手架自己做体检
bin/ratchet-audit      减法审计 —— 棘爪释放的数据来源
lib/transcript.py      transcript 共享解析器
hooks/hooks.json       双平台共用（一份两用）
skills/                init · handoff · ratchet · slim
templates/constitution.md   纪律基线（硬上限 4 KB）
schema/state.schema.json
```

`bin/` 下全是**平台无关的确定性脚本，零外部依赖**。CC 的 hook、Codex 的 hook、CI、命令行，只是触发同一套脚本的不同方式。这是整个设计的支点 —— 把不稳定的模型推理卸载为确定性代码。

## 跨平台

一份 `hooks/hooks.json` 两个平台共用。实测得出的兼容规则：

- **顶层只能有 `description` 和 `hooks`。** 出现 `$schema` 或 `_comment`，Codex 会拒绝整个文件并**静默丢弃全部 hook**（这是个真实发生过的线上故障）
- **`matcher` 一律留空。** CC 的工具叫 `Bash`，Codex 走 shell exec —— 写死工具名会在 Codex 上悄悄失效。粗筛交给 matcher，真正的过滤在脚本里做
- Codex 注入 `CLAUDE_PLUGIN_ROOT` 兼容别名，所以 hook 脚本零修改复用
- Codex 无 subagent 概念 —— 需要并行子代理的能力在 Codex 侧退化为串行

## 测试

```bash
./test/run.sh     # 45 PASS
```

每个真实发生过的 bug 都在这里留下一条永远拦住它的断言。不写「下次注意」，写测试。
