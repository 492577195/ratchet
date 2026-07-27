---
name: feedback
description: 把 ratchet 自身的问题上报为 GitHub issue。当用户抱怨 ratchet 行为异常——「ratchet 又误拦了」「这是 ratchet 的 bug」「给 ratchet 提个 issue」「这个门禁/简报/留痕不对劲」——时使用。脚本采集环境事实，AI 补充会话语义，按 finding 标杆组装、脱敏、经用户确认后提交。用户自己项目的问题不要上报，那是 /ratchet:ratchet 的本地棘轮。
---

# 反馈：让现场的问题，变成仓库里可消化的 issue

ratchet 装在各个项目里跑，**问题暴露在现场，修复在 ratchet 仓**。没有这条管道时，
finding 靠人手搬运，上下文丢一半，还没有状态跟踪——问题就这样蒸发掉。

这条管道：脚本采事实 → 你补语义 → 脱敏 → 用户确认 → 提交。

## 什么时候用 / 不用

**上报**（走这里）：问题在 ratchet 的机制本身——guard / digest / brief / state / init /
overhead / hooks / 某个 skill 的行为。

**不上报**：用户自己项目的纪律问题、本次任务本身的失误。那是 `/ratchet:ratchet` 的
本地棘轮，就地消化，不出项目。

判断不准时问用户，不要自己定。

## 第零步：一次只报一个问题

对话里浮现第二个问题？记下来，本轮结束后再跑一轮。
混报的 issue 无法「一次消化一个」，triage 端会退化成又一轮分拣。

## 第一步：机械采集

```bash
ratchet-feedback collect
```

输出 JSON：版本 / OS / python / 项目档位 / state 摘要 / hits 尾行 / overhead 报告。
**这些事实不许手抄、不许改写数字** —— 手抄就会每次编得不一样。
项目未 init 也能跑（报的可能就是 init 自身的 bug）。

## 第二步：平台必须问

collect 的 `platform` 恒为 `unknown`，这是刻意的：CC/Codex 没有可靠的进程内判别事实，
**脚本不猜，你也不许猜**。用 AskUserQuestion 问，选项对齐 issue 模板：

- Claude Code / OpenAI Codex / 两个都复现 / 命令行直接跑 bin/ 脚本

版本不问 —— 以 collect 的 `ratchet_version` 为准。

## 第三步：组装 finding

质量标杆是 plugin 仓库里的 `docs/finding-hits-无命令原文.md`（本 skill 的 `../../docs/` 下）
——先读它，照它的密度写。结构按这个模板（与 issue 模板字段对齐，lint 校验加粗的五节）：

```markdown
## 环境
平台: <第二步问的> · 版本: <collect 的> · 档位: <collect 的，未 init 写「未初始化」>
## 一句话
<因果链：X 导致 Y 退化成 Z>
## 场景与证据链
<什么项目、在做什么时触发。证据必须 file:line + 代码原文摘录 —— 不许凭印象引代码>
## 影响
<这个缺陷让什么机制失效/退化>
## 期望行为
<改成什么样算修好>
## 最小复现
<能构造就给 shell 命令（如 echo '{...}' | ./bin/ratchet-xxx），不能就写「待复现」>
## 已排除的错误方向
<为什么不该修 X —— 防止维护者走岔路。没有就写「无」>
## 修复方向（供参考，非强制）
<取舍点列给维护者定>
## 回归测试建议
<test/run.sh 里该加一条什么断言 —— 没有测试的约束不算约束>
## 补充
<collect 里的相关摘录：state/hits/overhead。无关的一律不放>
```

草稿写到 `mktemp` 临时文件，**不落用户项目目录** —— 落进去会污染用户的 git 状态。

## 第四步：脱敏

```bash
ratchet-feedback lint --file <草稿>
```

error（密钥、缺必需小节）必须改完重跑，**lint 没有豁免开关**。
warning（用户目录绝对路径）逐条与用户确认后改 `~`。

lint 扫不到的语义层，你负责人工过一遍：
公司内网域名/IP、他人项目名与同事 ID、hits 原文里命令可能夹带的敏感串、
**transcript 只许摘关键片段，绝不整段上传**。

## 第五步：用户确认（红线）

用 AskUserQuestion 展示：title 全文、body 全文、目标仓库、label。
**未经确认不提交。改一个字都要重新确认。**

## 第六步：提交，返回 URL

```bash
ratchet-feedback submit --file <草稿> --title '[<组件>] <一句话>'
```

title 前缀组件取自：`[guard] [digest] [init] [brief] [state] [audit] [overhead] [context] [hooks] [skill] [docs]`。

成功后把 issue URL 给用户。失败按退出码解释：

- `2`：没有 gh 或未认证 → 让用户跑 `gh auth login`，或把 body 文件路径留给用户手动贴
- `1` 且 gh 报权限：ratchet 仓是私有仓，需要协作权限 —— 同上兜底

删掉临时草稿。

## 第七步：本地衔接

告诉用户两件事：

1. issue 由 ratchet 工程侧的 `/ratchet:triage` 消化，可追踪状态
2. 如果这个问题本地有规避法（写条规则绕过），现在可以跑 `/ratchet:ratchet` 先止血，不等上游修复

## 红线汇总

- **未经确认不提交** —— 没有例外
- **一个 issue 只报一个问题**
- **平台不许猜** —— collect 给 unknown 就去问
- **transcript 不整段外传** —— 只摘关键片段
- **lint error 无豁免** —— 改完再跑就是正路
