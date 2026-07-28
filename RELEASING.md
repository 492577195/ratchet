# 发布

## 分支

```
main    正式版。用户装的就是它。永远绿
dev     日常开发。测试版
fix/*   hotfix：从 main 切，合回 main，再把 main 合回 dev
```

不用 Git Flow 的 release/hotfix 分支——单人项目上那是纯仪式负担，正是 ratchet 反对的「机制吃掉任务」。

## 开发时怎么验：`--plugin-dir`

**别为了验证而先合并 main。** 那会把没验过的代码推给所有项目——user-scope 的 plugin 在你每个仓里都活着。

```bash
cd /path/to/ratchet
claude --plugin-dir .      # 用当前工作树（dev 分支）起一个会话
```

| | |
|---|---|
| **session only** | 只影响这一次启动的会话，不写任何全局配置 |
| **in-place** | 只有 *marketplace* plugin 才拷贝进 `~/.claude/plugins/cache`。`--plugin-dir` 直接读目录——改完代码重启会话即生效，不用 bump version、不用 push |
| **不双注册** | 同名的 user-scope plugin 被覆盖，不是叠加。实测：一次 deny 只记一条 hit |
| **零污染** | 其他项目继续用 main 的稳定版 |

于是流程是：

```
dev + claude --plugin-dir .   ← 真实环境里随便崩
        ↓ 验过了
merge main → pre-push 门禁 → tag → /plugin update   ← 只有绿的才出门
```

**为什么必须真的起一个会话，而不是跑测试就算数**：v0.1.1 之前有四个 bug，47 条单元测试一个都没抓到——测试测的是「脚本算得对不对」，抓不到「平台认不认这个 hook 输出格式」。那类 bug 只有真跑才现形。

> 排查技巧：想确认加载的到底是工作树那份还是 cache 那份，往工作树的代码里塞一个唯一记号（如 `[DEV-PROBE-xxxx]`），跑一次看输出里有没有它。别靠猜。

## 门禁在哪

**GitHub Rulesets 需要 Team/Enterprise 计划，Free 用不了。** 所以 GitHub **不会**替你拦住任何东西——CI 能报红，但拦不住合并。

真正会拒绝你的只有一个：

```bash
git config core.hooksPath .githooks    # 克隆后跑一次，装上 pre-push
```

`pre-push` 会在推送前：

1. 跑 `test/run.sh` —— 不绿就拒绝，**任何分支，无例外**
2. 推 `main` 时追加发布检查：
   - 版本号**四处**一致（`VERSION` / `.claude-plugin/plugin.json` / `.codex-plugin/plugin.json` /
     `.claude-plugin/marketplace.json` 的顶层 `version` 与 `metadata.version`）
   - **版本号必须比最新 tag 新**
   - 宪法 ≤ 4 KB

能用 `--no-verify` 绕过。但那是显式的、有意识的选择——这就够了。软规则的问题从来不是"能不能绕"，而是"会不会被无意识地忽略"。

## 为什么必须 bump version

**Codex 的 plugin cache 路径是 `.../<plugin>/<version>/`，而且是物理拷贝（不是 symlink）。**

版本号不变 → 用户就算跑了 update，也还在用旧 cache → **拿不到你的新代码，而且完全没有报错**。

这是个静默失败，所以 pre-push 会硬拦。这不是我加的仪式，是 Codex 的 cache 机制倒逼出来的。

## 发布流程

```bash
# 1. 在 dev 上开发，测试绿
git checkout dev
./test/run.sh

# 2. bump 版本（四处必须一致 —— marketplace.json 有两个字段，别漏）
vim VERSION                          # 0.2.0
vim .claude-plugin/plugin.json       # "version": "0.2.0"
vim .codex-plugin/plugin.json        # "version": "0.2.0"
vim .claude-plugin/marketplace.json  # 顶层 version 与 metadata.version 都要改
./test/run.sh                        # 有断言校验四处一致，别等推 main 才被拦
git commit -am "[RELEASE] v0.2.0"

# 3. 合到 main
git checkout main
git merge --no-ff dev -m "[RELEASE] v0.2.0"

# 4. 推（pre-push 会在这里做全部发布检查）
git push origin main

# 5. 打 tag
git tag -a v0.2.0 -m "v0.2.0"
git push origin v0.2.0

# 6. main 回流 dev（保持同步）
git checkout dev && git merge main && git push origin dev
```

## 用户怎么升级

**Claude Code**

```
/plugin marketplace update ratchet
/plugin install ratchet@ratchet
```

**Codex**

```bash
codex plugin marketplace upgrade ratchet
codex plugin remove ratchet@ratchet
codex plugin add ratchet@ratchet     # cache 是物理拷贝，必须 remove 再 add
```

## 想给人测试版

Codex 支持指定 ref：

```bash
codex plugin marketplace add git@github.com:492577195/ratchet.git --ref dev
```

Claude Code 侧，`marketplace.json` 的 plugin source 支持 `ref` 字段锁定分支/tag/commit。但本仓的 plugin 就在 marketplace 仓内部（`source: "./"`），跟着 marketplace 的 checkout 走——所以直接 add 一个指向 dev 的 marketplace 即可。

本地开发时最简单：把 marketplace 指向仓库的绝对路径。

## 版本号约定

semver。默认 **patch+1**（新增功能也是），除非明确决定发 minor。

commit 前缀：`[FEATURE]` / `[FIX]` / `[BREAKING]` / `[DOC]` / `[REFACTOR]` / `[RELEASE]`。
