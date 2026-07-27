---
name: triage
description: 消化 ratchet 仓库里待办的 field-report issues：拉取、核实、修复、关闭。当在 ratchet 工程中说「处理上报」「triage」「看看有没有新 issue」「消化 feedback」时使用。核实先于改码，红断言先于修复，一次只消化一个。
---

# 分诊：让每一份现场上报都有一个确定的去向

`/ratchet:feedback` 把问题从现场送进了仓库。这一端负责消化：
**每个 issue 要么变成修复，要么变成明确的「不修」——不允许悬着。**

## 前置检查

三个条件，任一不满足就停下来报给用户，**不擅自 stash 或切分支**：

- 当前目录是 ratchet 仓
- 在 dev 分支（PR 提 dev，见 RELEASING.md）
- `git status` 工作树干净

## 第一步：拉取

```bash
gh issue list -R 492577195/ratchet --label field-report --state open
gh issue list -R 492577195/ratchet --state open   # 对照：降级提交的无 label issue 不能漏
```

`field-report` label 是主口径；**同时列一次全部 open** 作对照 ——
上报端 label 创建失败时会降级为无 label 提交，那些 issue 没有 label。

## 第二步：选定，一次一个

把编号 + 标题 + 日期列给用户，AskUserQuestion 选定。
**一次只消化一个** —— 与「一个 PR 只做一件事」同源。

## 第三步：核实（先于一切改动）

`gh issue view <N>` 读全文，在 dev 代码里找到 issue 指的 `file:line` 核对。
能写复现的，先写成 `test/run.sh` 的断言跑一遍——**红断言就是「复现成功」的证据**。

四个去向：

| 去向 | 判据 | 动作 |
|---|---|---|
| **现存缺陷** | 代码行为与 issue 描述一致 | 进第四步修复流 |
| **已修复** | 当前行为已对（issue 基于旧版本） | comment 给出「当前行为是 X」的验证证据，close |
| **工作流问题** | 机制按设计工作，痛点在使用方式 | comment 解释正确用法；值得就提议补文档，否则 close |
| **不修** | 修了代价大于收益 | **必须用户拍板**，comment 留理由，close |

finding-hits 里「为什么不该改去修切词误判」就是「工作流问题」的样板：
那是有意的 fail-closed，不是缺陷。

## 第四步：修复（红 → 绿）

1. 先在 `test/run.sh` 加断言并跑红（CONTRIBUTING 硬要求：每个真实 bug 留一条永远拦住它的断言）
2. 修实现
3. `./test/run.sh` 全绿
4. 行为改了同步 README；顺手 `bin/ratchet-overhead` 确认没撑大热区

## 第五步：提交与关联

commit message：`[FIX] <什么> Refs #<N>`。

**注意 auto-close 的时机陷阱**：GitHub 只在提交落到**默认分支 main** 时才执行
`Fixes #N` 的自动关闭，而本仓 PR 先进 dev、release 才合 main。
所以 dev 阶段用 `Refs #N`（只关联不关闭）；`Fixes #N` 留给合 main 的 release commit，
或 release 后手动 close。push 后立即 `gh issue comment <N>` 留 commit SHA ——
让上报者能追踪到「我的问题修在哪个提交」。

## 第六步：一类错，还是一个个案？

如果 issue 揭示的是**一类错**而非个案（协议类 bug 已经栽过两次的前科就在眼前），
按 `/ratchet:ratchet` 的标准问自己：能不能写成校验器/断言，让同类错在逻辑上无法重演？

triage 的修复流，本质上就是棘轮在 ratchet 仓自身上跑一遍 —— 回归测试就是那条棘轮。

## 红线

- **不核实不改码** —— 先核对 file:line，先写红断言
- **一次只消化一个**
- **close 必须留说明** —— 证据或理由，不许裸关
- **wontfix 必须用户拍板** —— 不修是一个决策，不是沉默
