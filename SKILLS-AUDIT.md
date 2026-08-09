# Skills 审查报告

审查日期：2026-08-09
仓库：`/Users/luyong/.cc-switch/skills`（macOS，git 分支 `main`，HEAD `d5d0095`）

## 范围

本报告审查当前仓库中的 **20 个 skill**，回答两个问题：

1. 按当前前沿 coding agent（GPT-5.6 / Claude Opus 5 级别）的能力，哪些 skill 已无必要或约束过度。
2. 这些 skill 是否适配本机实际安装的四个 Agent CLI。

实测环境：

| 组件 | 版本 | 备注 |
| --- | --- | --- |
| Pi Agent | 0.84.1 | 支持 `--skill <path>`、`--no-skills` |
| Codex CLI | 0.147.0 | 自带 `.system` skill 与 `codex review` |
| OpenCode | 1.18.15 | 未安装任何第三方插件 |
| Claude Code | 2.1.220 | 本次审查新增的第四个宿主 |
| OpenSpec CLI | 未安装 | 影响两个 OpenSpec 相关 skill |

cc-switch 配置（`~/.cc-switch/settings.json`）：

```json
{
  "skillSyncMethod": "auto",
  "skillStorageLocation": "cc_switch"
}
```

## 与上一版报告的关键差异

上一版报告的多处前提已经不成立，本版据实修正：

1. **宿主从三个变成四个。** Claude Code 已接入，并且是当前唯一有 cc-switch 托管软链接的宿主。
2. **OpenCode 没有安装 Superpowers。** `~/.config/opencode` 只有 `@opencode-ai/plugin@1.15.5`，没有任何 Superpowers 目录或配置。上一版“OpenCode 已被 Superpowers 覆盖，故不部署通用工程 skill”的整段推理作废。
3. **OpenCode 会自动加载 `~/.claude/skills`。** 实测 `opencode debug skill --pure` 返回的 6 个非内建 skill 全部来自 `/Users/luyong/.claude/skills/`。“部署给 Claude Code”在默认配置下等同于“同时部署给 OpenCode”。
4. **上一版列出的 6 个失效软链接已不存在。** 四个 skill 目录下现在没有任何断链。
5. **`skillSyncMethod` 已从 `symlink` 改为 `auto`。**
6. **仓库新增 4 个内部领域 skill**：`gerrit`、`commit-bu1-sdk-gerrit`、`refresh-bu1-sdk-rules`、`update-bu1-sdk-issue-conclusion`。它们构成一个互相依赖的捆绑包，当前部署是**残缺**的（见“BU1-SDK 捆绑包”一节）。
7. **`redmine/references/redmine-api.md` 的旧路径问题已修复**，现在与主 skill 的“相对 skill 目录读取 `SECRET.md`”规则一致。

## 总体结论

当前 skill 集分三类：

1. **应保留的内部领域知识与确定性自动化**：Redmine/Gerrit 实例配置、BU1-SDK 规则快照事务、ADB 调试与安全规则、OpenSpec 安装脚本。这部分质量最高，也是 cc-switch 存在的主要理由。
2. **项目约定与特定产物**：`CONTEXT.md`/ADR 维护、架构 HTML 报告、跨 agent 交接文档。有价值，但需要去掉宿主假设。
3. **重复现代 coding agent 默认行为的通用工作流胶水**：实现、拆票、写 spec、研究。这部分应停止部署。

建议默认部署规模：**通用基线 6 个 + BU1-SDK 捆绑 3 个（仅相关宿主）+ 若干可选项**。按宿主折算约为 Pi 9-12 个、Codex 5-8 个、OpenCode 与 Claude Code 各 6-9 个。

源码保留与部署是两个独立判断。以下内容即使模型能力再强也值得保留：

- 模型预训练中不存在的内部系统事实（实例 URL、字段 ID、状态枚举、审计前缀）。
- 必须长期一致执行的组织规则（提交格式、结论结构、写审计）。
- 带脚本、模板、事务语义的确定性流程。
- 跨会话、跨 CLI 需要持久化的状态。

如果 skill 只是复述“先读代码、实现、测试、检查、汇报”，不应部署。

## 逐项建议

| Skill | 源码建议 | 部署建议与结论 |
| --- | --- | --- |
| `adb` | 保留 | 四端可部署。设备状态判断、证据分层、SELinux/HAL 检查和破坏性命令禁令都是领域知识。frontmatter 已通过 Codex 标准校验，正文无宿主假设，可作为共享 skill 的样板。 |
| `code-review` | 保留 | Pi/OpenCode 建议部署；Codex 可选（已有 `codex review` 与 `.system/review-agent`）；Claude Code 可选（已有 `/review`、`/security-review`）。三轴分离 + 证据契约是真实约束，`SKILL.md:86` 已把并行子代理写成能力描述而非工具名，是正确写法。 |
| `codebase-design` | 保留，与架构 skill 同进同出 | 只在部署 `improve-codebase-architecture` 时一起链接。词汇表本身有价值；`DESIGN-IT-TWICE.md` 的 Agent 工具假设已在第二阶段改为能力描述。“禁止使用 service / API / boundary”仍偏僵硬。 |
| `commit-bu1-sdk-gerrit` | 必须保留 | 只给实际做 BU1-SDK 的宿主（当前是 Pi）。必须与 `redmine`、`refresh-bu1-sdk-rules` 同时部署，否则阶段零和快照路由分支无处落地。 |
| `domain-modeling` | 保留 | 四端可部署。`CONTEXT.md`、ADR 触发标准、以及“文档语言跟随既有语料、默认简体中文”的写作规则都是项目约定，模型通用能力无法替代。 |
| `gerrit` | 必须保留 | 四端可部署。两套实例、Digest/Basic 差异、XSSI guard、`commit:` 查询、分页与 TLS 例外全是内部知识。`SKILL.md:184` 的 “Agent-host compatibility” 段落是全仓库最好的宿主无关写法，应作为其他 skill 的改写模板。**当前 Pi 未链接它，是真实缺口。** |
| `grill-with-docs` | 合并（用户已决定暂缓） | 不单独部署。第二阶段已把 slash 调用改为宿主无关表述，但正文仍只是 `grilling` + `domain-modeling` 的组合入口；合并进 `grilling` 的动作按用户决定暂不执行。 |
| `grilling` | 保留 | 四端可部署。“一次一个问题、事实自己查、决策等用户”是可观测的行为约束，不是默认行为。建议限定在设计决策场景，不阻塞普通实现。 |
| `handoff` | 保留、标准化 | 四端可部署，本机同时装 4 个 CLI，交接文档是真实需求。应移除非标准 `argument-hint`，把参数语义写进正文，并明确输出路径与文件名。 |
| `improve-codebase-architecture` | 保留 | 四端可选。可视化 HTML 架构报告是独特产物。第二阶段已把 `Agent tool with subagent_type=Explore` 与 `SKILL.md`/`HTML-REPORT.md` 中的 5 处 slash 调用改为宿主无关表述。 |
| `install-openspec-superpowers-bridge` | 保留、暂停部署 | 本机未安装 OpenSpec CLI，也没有任何宿主装了 Superpowers，部署后无法验证。等真正采用 OpenSpec 再启用。安装脚本与升级 diff 本身质量可以，`SKILL_DIR` 解析方式正确。 |
| `openspec-language-config` | 保留、暂停部署 | 同上。另外 description 仍只提 “Codex”，应改成 agent 或写入 `metadata.compatibility`。 |
| `prototype` | 保留 | 四端可部署。UI 多方案与逻辑状态机两个分支有价值。规则 6 的强制提交已在第三阶段降级为建议，并要求跟随仓库自身惯例。 |
| `redmine` | 必须保留 | 四端可部署。实例 URL、`SECRET.md` 相对解析规则、审计前缀 `由 luyong-AI 操作：`、状态 ID 表都是内部知识。注意 `redmine/SECRET.md` 当前在本机不存在，凭据未配置前所有依赖它的流程都会失败。 |
| `refresh-bu1-sdk-rules` | 必须保留 | 唯一负责在线读取并维护本地规则快照的 skill，带 `.refresh.pending` 事务标记、staging 目录和原子替换。必须与两个业务 skill 同时部署。 |
| `tdd` | 可选 | 参考材料（seam 定义、反模式、tracer bullet、垂直切片）有真实价值。第三阶段已把 seam 确认从“每个测试前”放宽到“开工前一次约定，seam 集合变化时才回头问”，并把 refactor 改回红绿循环的第三拍。 |
| `to-tickets` | 保留 | 垂直切片与 expand-contract 宽重构序列是真知识。第三阶段已接入 `redmine`：Redmine 为默认 tracker，`ready-for-agent` 用标题前缀表达，blocking 边用 `blocks` 关系；未配置 tracker 时仍退回 step 5 的本地文件形式。 |
| `update-bu1-sdk-issue-conclusion` | 必须保留 | Gerrit change 的四层确定性匹配、严格输入解析、写前复核和写审计都是无法由模型推断的组织规则。依赖 `redmine`、`gerrit`、`refresh-bu1-sdk-rules` 三者。 |
| `wayfinder` | 保留 | 只给承担跨多会话大型规划的宿主。第三阶段已接入 `redmine`：map/ticket 类型用标题前缀，子问题用 `parent_issue_id`，blocking 用 `blocks` 关系，claim 用 `assigned_to_id`，frontier 查询给出了分页与"去掉被阻塞/已认领"的具体步骤；未配置 tracker 时仍退回 local-markdown。**Pi 已有本地个人变体（真实目录，非软链），不要用 cc-switch 版本覆盖。** |
| `writing-great-skills` | 可选 | Codex 有 `.system/skill-creator`，该端不必链接。其他端按是否认可这套方法论决定；`GLOSSARY.md` 的失败模式词汇本身质量不错。 |

## BU1-SDK 捆绑包

四个内部 skill 构成一个有向依赖图，**必须整体部署**：

```text
commit-bu1-sdk-gerrit ──需要──> redmine
                      ──路由──> refresh-bu1-sdk-rules

update-bu1-sdk-issue-conclusion ──需要──> redmine
                                ──需要──> gerrit
                                ──路由──> refresh-bu1-sdk-rules

refresh-bu1-sdk-rules ──需要──> redmine
```

当前 Pi 只链接了 `commit-bu1-sdk-gerrit`、`update-bu1-sdk-issue-conclusion`、`redmine`，**缺少 `gerrit` 和 `refresh-bu1-sdk-rules`**。后果是具体的：

- `update-bu1-sdk-issue-conclusion` 的第 5 步要求“通过 Gerrit skill 做确定性匹配”，缺 `gerrit` 时该步骤没有可依据的查询契约。
- 两个业务 skill 在快照过期或元数据无效时都要求“停止并路由到 `refresh-bu1-sdk-rules`”，缺该 skill 时用户被引导到一个不存在的入口。
- 两处正文使用相对路径 `../refresh-bu1-sdk-rules/SKILL.md` 引用兄弟 skill。这在 cc-switch 逐个建软链接的部署模型下**只有整套部署时才成立**。

建议在 cc-switch 中把这四个（含 `redmine`）作为一个部署单元处理，或至少在文档中标注为必须同进同出。

## cc-switch 管理模型

本目录是 **skill 源码仓库**，不是任何宿主的实际加载目录。cc-switch 以 SQLite（`~/.cc-switch/cc-switch.db`）记录每个 skill 的按宿主启用状态：

```sql
CREATE TABLE skills (
  id, name, description, directory, ...,
  enabled_claude, enabled_codex, enabled_gemini,
  enabled_opencode, enabled_hermes, enabled_grokbuild, ...
);
```

两点需要注意：

1. **没有 `enabled_pi` 列。** Pi 的 12 个软链接不在 cc-switch 的托管范围内，是手工或旧版本留下的。这解释了为什么 Pi 的部署集与数据库状态完全对不上，也是 BU1-SDK 捆绑残缺的直接原因。要么把 Pi 纳入 cc-switch，要么明确把 Pi 作为手工维护的宿主并单独记录清单。
2. **cc-switch 数据库有孤儿行。** 第三阶段删除了三个 skill，其中两个在 `skills` 表中仍有记录（均为全部宿主禁用）。磁盘 20 个、数据库 22 条，需要在 cc-switch 侧清理。

“源码存在但没有给某宿主生成链接”是正常状态，不属于漏装。只有下面两种情况才是故障：

- 用户在 cc-switch 中明确启用了某项，但链接没有生成。
- 链接存在但目标不存在（断链）。当前四个目录下**没有断链**。

## 建议部署矩阵

`链接` = 建议部署，`可选` = 只在实际工作流需要时部署，`不链接` = 建议不部署。

| Skill | Pi | Codex | OpenCode | Claude Code |
| --- | --- | --- | --- | --- |
| `adb` | 链接 | 链接 | 链接 | 链接 |
| `code-review` | 链接 | 可选（有 `codex review`） | 链接 | 可选（有 `/review`） |
| `codebase-design` | 可选（随架构 skill） | 可选（随架构 skill） | 可选（随架构 skill） | 可选（随架构 skill） |
| `commit-bu1-sdk-gerrit` | 链接 | 可选 | 不链接 | 不链接 |
| `domain-modeling` | 链接 | 链接 | 链接 | 链接 |
| `gerrit` | **链接（当前缺失）** | 链接 | 链接 | 链接 |
| `grill-with-docs` | 不单独链接 | 不单独链接 | 不单独链接 | 不单独链接 |
| `grilling` | 链接 | 链接 | 链接 | 链接 |
| `handoff` | 链接 | 链接 | 链接 | 链接 |
| `improve-codebase-architecture` | 可选 | 可选 | 可选 | 可选 |
| `install-openspec-superpowers-bridge` | 暂停 | 暂停 | 暂停 | 暂停 |
| `openspec-language-config` | 暂停 | 暂停 | 暂停 | 暂停 |
| `prototype` | 链接 | 链接 | 链接 | 链接 |
| `redmine` | 链接 | 链接 | 链接 | 链接 |
| `refresh-bu1-sdk-rules` | **链接（当前缺失）** | 可选 | 不链接 | 不链接 |
| `tdd` | 可选 | 可选 | 可选 | 可选 |
| `to-tickets` | 可选 | 可选 | 可选 | 可选 |
| `update-bu1-sdk-issue-conclusion` | 链接 | 可选 | 不链接 | 不链接 |
| `wayfinder` | 保留本地个人变体 | 可选 | 可选 | 可选 |
| `writing-great-skills` | 可选 | 不链接（有 `skill-creator`） | 可选 | 可选 |

这张表是默认策略，不是硬编码规则。cc-switch 应允许针对单个宿主覆盖。

**重要约束：OpenCode 列与 Claude Code 列不是独立的。** 在默认配置下 OpenCode 自动加载 `~/.claude/skills`，两列实际耦合。要让它们真正独立，需要在 `opencode.json` 中用 `skills.paths` 指定独立目录，或接受二者一致。

## 四个 CLI 的发现目录

```text
Pi:          ~/.pi/agent/skills/<name>            （另支持 pi --skill <path>）
Codex:       ~/.codex/skills/<name>               （内建集在 ~/.codex/skills/.system）
OpenCode:    ~/.config/opencode/skill(s)/<name>   （全局）
             .opencode/skill(s)/<name>            （项目级）
             ~/.claude/skills/<name>              （外部，自动加载）
             ~/.agents/skills/<name>              （外部，自动加载）
             opencode.json 的 skills.paths / skills.urls
Claude Code: ~/.claude/skills/<name>
```

OpenCode 的目录列表由其内建 `customize-opencode` skill 给出，已实测确认 `~/.claude/skills` 分支生效。

`~/.agents/skills` 适合真正需要同时暴露给多个宿主的最小公共集合（当前为空），但不适合无差别链接整个仓库。使用宿主专属目录更容易表达“这个 skill 只给 Pi，不给 Codex”。

## 当前链接状态

### Pi（12 个软链接 + 2 个本地目录，不受 cc-switch 托管）

```text
软链接: adb, code-review, commit-bu1-sdk-gerrit, domain-modeling,
        grill-with-docs, grilling, handoff, improve-codebase-architecture,
        prototype, redmine, update-bu1-sdk-issue-conclusion, writing-great-skills
本地目录: impl-with-spawn, wayfinder
```

问题：BU1-SDK 捆绑残缺（缺 `gerrit`、`refresh-bu1-sdk-rules`）；`grill-with-docs` 单独部署但正文用 slash 语法调用两个 skill，其中 `codebase-design` 并未链接到 Pi。

### Codex（0 个 cc-switch 链接）

`~/.codex/skills` 下只有 `.system`：`imagegen`、`openai-docs`、`plugin-creator`、`review-agent`、`skill-creator`、`skill-installer`。数据库中所有 `enabled_codex` 均为 0，状态一致，不是故障。

### OpenCode（0 个专属链接，6 个经 `~/.claude/skills` 自动加载）

`~/.config/opencode/skills` 不存在。实测加载到 `codebase-design`、`domain-modeling`、`grill-with-docs`、`grilling`、`handoff`、`improve-codebase-architecture`，全部来自 Claude Code 目录。这是**未经 cc-switch 记录的隐式部署**，数据库中 `enabled_opencode` 全为 0 与实际不符。

### Claude Code（6 个软链接，与数据库一致）

```text
codebase-design, domain-modeling, grill-with-docs, grilling,
handoff, improve-codebase-architecture
```

### 断链

四个目录下**均无断链**。上一版报告列出的失效链接已全部清理。

## Frontmatter 兼容性

用 Codex 自带 `skill-creator/scripts/quick_validate.py` 的规则校验（该脚本本身因缺 `pyyaml` 无法直接运行，按其 `allowed_properties` 等价复现）：**20 个 skill 中 11 个未通过**。

允许字段集合为：

```text
name, description, license, allowed-tools, metadata
```

未通过原因全部是宿主扩展字段：

- `disable-model-invocation: true` — 13 个 skill 使用
- `argument-hint: "..."` — 仅 `handoff` 使用

通过校验的 9 个：`adb`、`code-review`、`codebase-design`、`domain-modeling`、`gerrit`、`grilling`、`prototype`、`redmine`、`tdd`。

各宿主实际表现（本次已实测）：

- **Claude Code 支持 `disable-model-invocation`。** 本仓库链接给它的 6 个 skill 中，带该字段的 3 个（`grill-with-docs`、`handoff`、`improve-codebase-architecture`）确实不出现在模型可自动调用的列表里，只保留手动调用。
- **OpenCode 会忽略该字段的语义。** `opencode debug skill` 把这 6 个全部发现并列出，包括带该字段的 3 个。
- **Codex 的官方校验器把它报为 unexpected key。**
- **Pi 加载宽松**，接受该字段。
- `agents/openai.yaml` 只对 Codex/ChatGPT 的 UI 与隐式调用策略生效，Pi、OpenCode、Claude Code 会忽略。当前 `handoff/agents/openai.yaml` 已用 `policy.allow_implicit_invocation: false` 表达同一意图，这是 Codex 侧的正确写法。

跨宿主共享的 `SKILL.md` 应优先只用标准字段：

```yaml
---
name: skill-name
description: Explain what it does and when to use it.
license: MIT
metadata:
  compatibility: Requires tool X when applicable.
allowed-tools: read bash
---
```

通常只需 `name` 和 `description`。

如果跨宿主一致性优先，不要依赖“仅手动调用”这一扩展语义，因为 OpenCode 不认。更稳妥的组合是：

- 收紧 `description` 的触发条件，让模型按需加载。
- 在 Codex 侧用 `agents/openai.yaml` 的 `policy.allow_implicit_invocation` 表达。
- 对真正危险的 skill 用宿主权限配置约束，而不是只靠 frontmatter。

## 跨 skill 调用不兼容（第二阶段已修复）

原先 5 个文件 17 行使用 slash 语法跨 skill 调用；其中 4 个文件仍在仓库中（`grill-with-docs`、`improve-codebase-architecture/SKILL.md` 与 `HTML-REPORT.md`、`wayfinder`），第 5 个已在第三阶段随 skill 整体删除。这些不是通用协议：Pi 显式加载通常用 `/skill:<name>`，Codex 用 `$<skill-name>`，OpenCode 与 Claude Code 由模型调用原生 skill 工具。

现已全部改为宿主无关表述，统一采用仓库内既有写法：

```text
Load and follow the available Redmine skill for authentication, issue API usage,
the conclusion custom field, and write-audit requirements. Use the host's native
skill-loading mechanism; do not assume a slash command or a particular Agent API.
```

（`update-bu1-sdk-issue-conclusion/SKILL.md:11`）

现存的三个文件（`grill-with-docs`、`improve-codebase-architecture/SKILL.md`、`wayfinder`）另外补了一句统一说明：命名的 skill 通过宿主原生机制加载，不假设 slash command、`$name` 语法或特定 Agent API；该 skill 在本宿主不可用时，**只告诉用户缺哪一个** —— 不概括被引用 skill 的内容，也不内联替它执行。前者是 duplication（被引用方一改就失配），后者等于让 agent 假装拥有它没有的能力。第三阶段接入 Redmine 时，`to-tickets` 与 `wayfinder` 的 Redmine 段落沿用了同一句式。

`prototype/UI.md:75` 的 `/prototype/<name>` 是 URL 路由路径，不是 skill 调用，不在此列。

后续新增内容应保持这一约定。对只有一两句话的依赖，直接内联规则，不要为此形成跨 skill 依赖。

## 子代理接口不兼容（第二阶段已修复）

原先两处写死具体工具名：`improve-codebase-architecture/SKILL.md` 的 `use the Agent tool with subagent_type=Explore`，以及 `codebase-design/DESIGN-IT-TWICE.md` 的 `Spawn 3+ sub-agents in parallel using the Agent tool`。

四个宿主的能力不同：Pi 核心没有统一的 `Agent` 工具（可通过 `interactive_shell` 扩展启动子会话）；Codex 有 `multi_agent` 但接口名不同；OpenCode 用 `task` 工具；Claude Code 用 `Agent` 工具（名字恰好相同，但不能作为共享 skill 的前提）。

两处现已改为能力描述：

- `improve-codebase-architecture` — “宿主支持隔离子代理时委派给它们，否则在当前会话内联探索”。
- `codebase-design/DESIGN-IT-TWICE.md` — “宿主支持时并行跑隔离子代理，否则顺序产出，但保持各设计的 brief 与输出彼此隔离，避免后一个设计被前一个锚定”。同时把 `### 2. Spawn sub-agents`、`Agent 1..4` 等只在有子代理时才成立的措辞改为 `### 2. Produce the designs`、`Design 1..4`。

仓库内的两处正确示范仍是改写模板：

- `code-review/SKILL.md:86` — “Run the three lanes in parallel when the environment supports isolated sub-agents… If parallel sub-agents are unavailable, run the lanes sequentially with separate prompts and preserve the same boundaries.”
- `gerrit/SKILL.md:184` — 完整的 “Agent-host compatibility” 段落。

只有 Pi 专用 skill 才应明确写 `interactive_shell`。

## 过度确认和强制提交

强模型下以下确认会无谓中断工作。第三阶段已处理仓库内的三处：

- ~~每写一个测试前确认 seam。~~ 已放宽为开工前约定一次 seam 集合，只在集合本身变化时回头问。
- ~~原型完成后强制提交到 throwaway branch。~~ 已降级为建议，并要求跟随仓库自身惯例。
- ~~实现结束后无条件提交当前分支。~~ 承载该规则的 skill 已在第三阶段删除。
- 普通规划中的所有决策逐一等待批准 —— 仍是写新 skill 时要避开的模式。

确认应保留在这些情况，当前内部 skill 在这方面做得是对的：

- 外部系统写操作（Redmine `PUT`、Gerrit `push`）。
- 删除、覆盖、重置、迁移等破坏性操作。
- 不可逆或成本很高的架构决策。
- 用户需求存在真实分支且无法从代码或既有约定推断。
- 准备发布、推送、创建 PR 或修改共享基础设施。

普通代码实现、测试选择和局部重构应由 agent 自主完成并验证。

## 具体内容问题

1. ~~4 处引用已删除的安装类 skill。~~ **第二阶段已修复**，其中两个承载文件已在第三阶段整体删除，`to-tickets` 与 `wayfinder` 改为“tracker 来自项目自身配置，默认 Redmine，未配置时退回本地形式”。
2. ~~`research` 不在 cc-switch 数据库中。~~ 该 skill 已在第三阶段删除；现在的问题反向了：数据库里留有两条已删除 skill 的孤儿记录（磁盘 20 / 数据库 22），需在 cc-switch 侧清理。
3. **`redmine/SECRET.md` 在本机不存在**（已被 `.gitignore` 正确排除，也未进入 Git 跟踪）。凭据未配置前，`redmine`、`refresh-bu1-sdk-rules`、两个 BU1-SDK 业务 skill，以及第三阶段新接入 Redmine 的 `to-tickets`、`wayfinder` 都会在第一步失败。
4. **`~/.config/opencode/opencode.json` 中存在明文 provider API key。** 与本仓库无关，但既然 OpenCode 会自动加载 `~/.claude/skills`，任何被部署的 skill 都可能在该目录附近工作，值得单独收敛到环境变量或凭据文件。
5. ~~`to-spec` 强制“extremely extensive”的用户故事清单。~~ 该 skill 已在第三阶段删除。
6. ~~`prototype` 与 `implement` 中的强制 branch/commit 行为。~~ `prototype` 已降级为建议；`implement` 已删除。
7. `openspec-language-config` 的 description 仍只提 “Codex”，应改成 agent 或写入 `metadata.compatibility`；`install-openspec-superpowers-bridge` 已经用 `metadata.compatibility` 表达，可作为参照。
8. `handoff` 的 `argument-hint` 是非标准字段，语义应改写进正文。
9. **正文语言不统一**：`refresh-bu1-sdk-rules` 全中文，`commit-bu1-sdk-gerrit` 英文正文 + 中文 shell 报错，`update-bu1-sdk-issue-conclusion` 全英文 + 中文交互契约。面向用户的报错和确认词用中文是刻意设计且正确，但三个同族 skill 的正文语言建议统一。
10. `codebase-design` 的“禁止使用 service / API / boundary”对通用代码库过于僵硬，建议改为“在本 skill 的讨论范围内使用这套术语”。

## 推荐修复顺序

### 第一阶段：修复部署状态（可立即执行，不改正文）

1. 补齐 Pi 的 BU1-SDK 捆绑：链接 `gerrit` 和 `refresh-bu1-sdk-rules`。
2. 清理 cc-switch 数据库里两条已删除 skill 的孤儿记录（磁盘 20 / 数据库 22）。
3. 决定 Pi 的托管方式：纳入 cc-switch，或明确标记为手工维护并单独记录清单。
4. 显式处理 OpenCode 与 Claude Code 的目录耦合：接受二者一致，或用 `opencode.json` 的 `skills.paths` 分离，并让 cc-switch 的 `enabled_opencode` 反映真实状态。
5. 配置 `redmine/SECRET.md`，否则四个内部 skill 全部不可用。
6. 保留 Codex 的 `.system` skill 和 Pi 的本地 `wayfinder`、`impl-with-spawn`，不要被 cc-switch 覆盖。

### 第二阶段：删除失效引用（已完成，2026-08-09）

1. ✅ 删除 4 处对已删除安装类 skill 的引用，并给每处补上无 tracker 时的退路。
2. ✅ 把 5 个文件 17 行 slash 跨 skill 调用改成宿主无关表述，其中 4 个文件另加一句统一说明：`If a named skill is unavailable here, tell the user which one is missing.`
3. ✅ 把 2 处写死的 `Agent` 工具调用改成能力描述，照 `code-review/SKILL.md:86` 与 `gerrit/SKILL.md:184` 的写法。
4. ⏸ 合并 `grill-with-docs` 进 `grilling` — 用户决定暂缓，两个 skill 继续各自存在。

### 第三阶段：按宿主去重与放宽（已完成，2026-08-09）

1. ✅ `implement`、`to-spec`、`research` 从源码仓库直接删除（不是停止部署）。删除前确认四个宿主都没有指向它们的软链接，删除后 `wayfinder` 里两处对 `research` skill 的引用改为内联描述，避免产生新的悬空引用。
2. ✅ 放宽 `tdd`：seam 确认从“每个测试前”改为“开工前约定一次，只在 seam 集合变化时回头问”；`Refactoring is not part of the loop` 改回红绿循环的第三拍（绿灯下重构，限本轮触及的代码，跨模块重构仍需上浮）。放宽 `prototype` 规则 6：强制提交改为建议，并要求跟随仓库自身惯例。
3. ✅ Codex 不部署 `writing-great-skills` 与 `code-review` — 用户确认，属部署决策，无正文改动。
4. ⏸ 不合并 `codebase-design` 进 `improve-codebase-architecture` — 用户决定，两者继续同进同出但保持独立。
5. ✅ `to-tickets` 与 `wayfinder` 保留并接入 `redmine`。Redmine 无原生 label，统一用标题前缀表达；blocking 用 `blocks` 关系（Redmine 会阻止关闭被阻塞的问题，`precedes` 只挪日期不强制任何东西）；本地 markdown 分支保留为无 tracker 时的退路。为此在 `redmine/references/redmine-api.md` 补充了缺失的问题关系 API（GET/POST/DELETE），让 Redmine API 事实留在拥有它的 skill 里，而不是复制进两个调用方。

### 第四阶段：格式标准化与验证

1. 共享 skill 的 frontmatter 只保留 `name`、`description`（必要时 `license`、`metadata`、`allowed-tools`）。
2. 把“仅手动调用”的意图迁移到 `agents/openai.yaml` 的 `policy.allow_implicit_invocation` 与宿主权限配置。
3. 用 Codex `quick_validate.py` 的规则重新校验全部共享 skill（需先安装 `pyyaml`）。
4. 用 `opencode debug skill --pure` 确认 OpenCode 的发现结果与预期一致。
5. 在 Pi 中检查 available skills 和 `/skill:<name>`；在 Claude Code 中确认自动调用列表与 `disable-model-invocation` 的预期一致。
6. 为每个保留的 skill 准备至少一个应触发案例和一个不应触发案例。
7. 确认四个宿主不会同时加载同名但内容不同的 skill（`wayfinder` 是现存唯一案例）。

## 最终原则

一个 skill 是否保留在 cc-switch 源码仓库，与是否部署给某个宿主，是两个独立判断。

保留在源码仓库需至少满足一项：

- 提供模型不知道的领域事实。
- 固化必须长期一致执行的组织约束。
- 提供脚本、模板或确定性工具。
- 产生普通对话无法替代的特定 artifact。
- 为跨会话工作提供可靠的持久状态。
- 经实际使用证明，能纠正当前模型仍会反复出现的具体失败模式。

不要仅因为某个流程“看起来专业”就把它部署给所有宿主。对当前级别的 agent，短而准确的项目约定通常比一套互相调用的通用工作流更可靠。cc-switch 的价值正是在统一保存源码的同时，按每个宿主的原生能力、插件和实际失败模式生成不同的部署集合。
