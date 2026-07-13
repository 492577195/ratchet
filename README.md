# ratchet

**AI 协作工程脚手架。** 跨 Claude Code 与 OpenAI Codex。

把靠模型自觉遵守的工程纪律，下沉成拦得住的确定性门禁 —— 并且保证机制自身的上下文开销**不随项目年龄增长**。

```
危险动作 rm -rf        → 直接拒绝，不是提醒       ✅
幻觉包 pip install     → 拦下来问你，不是装了再说  ✅
每次会话起手注入       → 674 B，永远不会变成 10 万 token ✅
```

**简单项目不要装** —— 这是最有效的防臃肿措施。它是给「跑得久、会话多、AI 会重复踩同一个坑」的项目用的。

---

## 装

⚠️ **本仓目前是私有仓。** 你需要满足两个前提，否则安装会失败：

1. 你已经是本仓的**协作者**（找仓库所有者加你）
2. 你本机已配好 **SSH key** 并能 `ssh -T git@github.com` 通过

必须用 SSH URL —— `492577195/ratchet` 这种简写会走匿名 HTTPS，被 GitHub 以 404 拒绝（私有仓对匿名请求表现为「不存在」，所以报错信息会很误导）。

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

## 5 分钟上手

**1. 在你的项目里初始化**

```
/ratchet:init
```

它会先问你档位（普通 / 复杂），再铺出 `.ratchet/`：

```
.ratchet/state.json        你的状态（唯一真源，永不被覆写）
.ratchet/constitution.md   纪律基线（plugin 产物，upgrade 会更新）
.ratchet/log/              会话留痕（自动生成）
.ratchet/rules/            你的自定义规则（/ratchet:ratchet 会往这里加）
```

> **Codex 用户注意**：Codex 没有自定义 slash 命令，靠 skill 的 description 自然语言触发 —— 直接说「初始化这个项目的工程脚手架」。下同。

**2. 填两个字段，就这两个**

打开 `.ratchet/state.json`，把 `current.task`（在做什么）和 `current.next`（下一步）填上。剩下的字段等有内容了再说。

**3. 之后什么都不用做**

下次开会话，起手简报自动注入；会话结束，留痕自动落盘。你只需要在**该用棘轮的时候用棘轮**：

| 什么时候 | 用哪个 | 它做什么 |
|---|---|---|
| AI 又犯了一次不该犯的错 | `/ratchet:ratchet` | 把这次失败转成**永久物理约束** —— 优先写成校验器，写不成才写规则 |
| 上下文用到 60–70%，任务告一段落 | `/ratchet:handoff` | 产出交接文件，然后安全 `/clear`，用干净上下文继续 |
| 规则越积越多，维护流程比干活还累 | `/ratchet:slim` | 做减法 —— 零命中的规则淘汰，高频命中的软规则升级成硬校验器 |

棘轮只进不退就是熵增引擎。**棘爪必须能松开** —— 所以 `/ratchet:slim` 和 `/ratchet:ratchet` 一样重要。

## 它长什么样

装完之后，你实际会看到这些东西。以下全部是真实输出，不是示意。

**每次会话开头，自动注入（`ratchet-brief`）**

```markdown
# 当前状态  ·  v0.1.3 / testing

**在做**：只读区 + 判据完整性兜底
**下一步**：eval 自循环（--loop）

## 🚫 阻塞
- Codex PreToolUse deny 未证实（2026-07-12 起） → 解除条件：额度恢复后用隔离环境补测

## 🗳️ 最近决策
- 判据仓对 AI 只读 —— 改判据比改代码容易
- 开发用 --plugin-dir 跑 dev —— in-place 加载，零污染

⚠️ 上次会话（s-2）的日志未写，先补写再开新工作。
```

**674 B** 📊。它由 `state.json` 机器渲染，**禁止手工编辑**，所以它不会过期 —— 而且 schema 的 `maxItems` / `maxLength` 在数学上保证它永远超不过 2 KB。

**AI 想跑危险命令时（`ratchet-guard`，PreToolUse）**

```
$ rm -rf ./src
→ deny：[ratchet-guard] 递归强制删除（rm -rf）。要删就明确列出路径，或让用户自己执行。

$ pip install requests-toolbelt-pro
→ ask：[ratchet-guard] 安装了依赖清单里没有的包 `requests-toolbelt-pro`。
   Slopsquatting 风险：模型会幻觉出不存在的包名，攻击者抢注同名恶意包，
   post-install 脚本可在毫秒级窃取本机凭据。
   请先确认它确实存在、是你要的那个包、且维护者可信，再放行。
```

这是**拒绝**，不是提醒。模型说服不了它，因为它不是模型。

**给脚手架自己做体检（`ratchet-overhead`）**

```
🔥 热区（每次会话可能进上下文 · 必须恒定）  10.9 KB
        3.8 KB  AGENTS.md
        1.1 KB  .ratchet/state.json
         413 B  CLAUDE.md

🧊 冷区（归档 · 只检索不加载 · 长多大都行）  4.9 KB

热区 10.9 KB / 预算 12.0 KB  (90%)  🟢 健康
```

机制税是可测量的，所以它可以被管住。

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

## 为什么会有这个东西

以上是怎么用。以下是它为什么长这样 —— 如果你只想用，可以不看。

这套东西是从一个真实工程里抽出来的 —— 那个工程用两个月、251 个会话，长出了一套完整的 AI 协作方法论，也长出了它的病。实测账单：

| | |
|---|---|
| 每次会话「起手必读」文件合计 | **247,366 B**（约 8–10 万 token） |
| 其中 `PLAN/current.md` 单文件 | **164,297 B**，且仍在增长 |
| 230 份 session 日志 | 1.86 MB |
| `CLAUDE.md` + `AGENTS.md` | 25 KB，每次会话全量进上下文 |
| 校验脚本 | 31 KB 的正则怪物，检查项从 ① 叠到 ⑪ |

**一个会话还没开始干活，起手仪式就吞掉近 10 万 token** ⚠️。而这条曲线是发散的。

更根本的问题：那 164 KB 里，真正「每次都需要」的决策信息只有 **4,311 B**。剩下 96% 是没人敢删的历史 —— 它们不是信息，是沉积物。

病根有两条：

1. **能机器化的工程纪律，被写成了靠模型自觉遵守的规则。** 而规则会退化 —— 修复方式往往是「再加一条规则」，于是规则膨胀、上下文稀释、更容易被忽略、再加规则。
2. **机制自身的上下文成本与项目年龄挂钩。** 跑上一年，起手仪式就会吃掉本该属于任务的上下文。

## 怎么治

**状态与叙述分离。**

- **状态**（在做什么 / 下一步 / 阻塞 / 待拍板 / 最近决策）→ `.ratchet/state.json`，机器读写，schema 校验
- **叙述**（日志 / 修订 / 复盘）→ Markdown，人和 AI 读，机器不解析
- **起手简报** → 由 state 自动渲染，**硬上限 2 KB，禁止手工编辑** —— 它不会过期，所以那 31 KB 正则脚本的大半检查项不是被修好，是不再需要存在

**冷热分离。** 热区（每次进上下文）必须恒定；冷区（归档）随便长。冷区膨胀无所谓，热区膨胀才是病。

**棘轮 + 棘爪。** 每次失败转化为永久物理约束（`/ratchet:ratchet`）—— 但棘轮只进不退，是熵增引擎，所以必须配套减法（`/ratchet:slim`）：规则带命中计数，长期零命中的淘汰，高频命中的升级成硬校验器。

## 效果

| | 原工程 | ratchet |
|---|---|---|
| 起手注入 | 247,366 B（发散 📈） | **最坏 1,834 B / 真实 674 B**（恒定 ✅） |
| 收尾模型手写 | 8 段 ≈ 8 KB | **≤ 1 KB**，其余机器生成 |
| 与项目年龄的关系 | 线性增长 | **无关**（schema 上限 + 冷热分离结构性保证） |

最坏情况的 1,834 B 不是「但愿如此」—— schema 的 `maxItems` / `maxLength` 在数学上保证渲染永远超不过它。装不下的东西会被机器拒绝，而不是靠人记得清理。

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

- **顶层只能有 `description` 和 `hooks`。** 出现 `$schema` 或 `_comment`，Codex 会拒绝整个文件并**静默丢弃全部 hook**（这是个真实发生过的线上故障 ⚠️）
- **`matcher` 一律留空。** CC 的工具叫 `Bash`，Codex 走 shell exec —— 写死工具名会在 Codex 上悄悄失效。粗筛交给 matcher，真正的过滤在脚本里做
- Codex 注入 `CLAUDE_PLUGIN_ROOT` 兼容别名，所以 hook 脚本零修改复用
- Codex 无 subagent 概念 —— 需要并行子代理的能力在 Codex 侧退化为串行

## 开发

克隆后跑一次，装上 pre-push 门禁：

```bash
git config core.hooksPath .githooks
```

它会在推送前跑测试、校验版本号一致性与宪法体积，不过就拒绝推送。
**这是唯一的真门禁** —— GitHub Rulesets 要 Team 计划，Free 版的私有仓用不了，
所以服务端不会替你拦住任何东西。详见 [RELEASING.md](./RELEASING.md)。

分支：`main` 正式版（用户装这个，永远绿）· `dev` 日常开发。

想参与请先读 [CONTRIBUTING.md](./CONTRIBUTING.md) —— 尤其是「什么样的改动会被拒绝」那一节。

## 测试

```bash
./test/run.sh     # 91 PASS / 0 FAIL
```

每个真实发生过的 bug 都在这里留下一条永远拦住它的断言。不写「下次注意」，写测试。

## 许可

MIT。见 [LICENSE](./LICENSE)。
