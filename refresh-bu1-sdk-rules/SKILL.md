---
name: refresh-bu1-sdk-rules
description: Refresh the local BU1-SDK Gerrit and Redmine rule snapshots from authenticated Redmine Wiki APIs, show rule changes, and update both snapshots only after explicit confirmation.
disable-model-invocation: true
---

# Refresh BU1-SDK Rules

这是唯一负责在线读取并维护 BU1-SDK 本地规则快照的 skill。`commit-gerrit` 和 `update-issue-conclusion` 在业务执行期间只读取本地快照，不访问在线 Wiki，不修改 reference 文件，也不检查快照版本、是否过期或刷新事务。需要更新时由用户手动调用本 skill。

## 规则来源

执行器通过 [Redmine CLI](../redmine/SKILL.md) 读取 Wiki，沿用它的请求头认证和凭据配置。

必须读取以下三个 API 页面，并从每个响应的 `wiki_page` 中取得 `text`、`version` 和 `updated_on`：
- `GET /projects/bu1-sdk/wiki/Gerrit%E4%BD%BF%E7%94%A8%E8%A7%84%E5%88%99.json`
- `GET /projects/bu1-sdk/wiki/Gerrit%E8%A1%A5%E4%B8%81%E7%94%9F%E6%88%90%E7%BB%86%E5%88%99.json`
- `GET /projects/bu1-sdk/wiki/Redmine%E4%BD%BF%E7%94%A8%E8%A7%84%E5%88%99.json`

一次刷新必须完整成功读取这三个页面。前两个页面的规则共同组成 `commit-gerrit` 的快照，第三个页面组成 `update-issue-conclusion` 的快照。刷新时保留本地 reference 的规则摘录结构，并同步每个来源页面的版本、更新时间和核对元数据；不要把 API key 或原始认证响应写入文件。

## 刷新流程

本 skill 的执行器是 `scripts/refresh.py`，子命令 `plan` / `apply` / `abort` / `status`。它经 **Redmine** skill 的 CLI（`redmine/scripts/redmine.py`，可用 `REDMINE_CLI` 覆盖路径）完成认证和在线读取；秘密处理遵守该 skill 的要求。写入授权走共享确认门禁：宿主协议、凭据状态目录、TTL 和执行边界见 [confirm-gate/README.md](../confirm-gate/README.md)。

1. **确认用户意图。** 本 skill 只在用户明确要求刷新规则，或由用户明确配置的外部调度器调用时运行，不依赖模型自唤醒实现定时器。展示当前本地快照版本和 `checked_at`；外部调度器也必须保留本 skill 的确认和失败策略。
2. **plan。** 先检查交互宿主是否提供 `confirm_gate`，再运行 `python3 scripts/refresh.py plan`（从本技能目录运行）。执行器检查门禁状态目录，并校验三个页面都有正文、正整数版本和带明确 UTC 时区的更新时间。随后原子写入事务标记 `.refresh.pending`，记录目标路径和替换前及候选的 SHA-256，再在各 reference 同目录写入 `<reference>.tmp-<UTC 时间戳>` 并登记 `action_id`。计划输出包括
   - 每个页面的版本、更新时间和在线全文 `pages[].text`——规则正文是人工摘录，审阅以在线全文为准；
   - 每个快照的 `diff`，规则正文与元数据分开比较，`rules_changed` 只由正文决定。
   任一页面读取或校验失败时，执行器删除本次临时文件和事务标记，原有 reference 不变，并报告失败原因。
3. **审阅来源变化。** 来源页面的版本无法与本地 `source_version` 核对一致时，执行器以 `sources_changed` 停止：只刷新元数据不能声称规则已更新。先对照本次输出的在线全文审阅，修订规则正文草稿，再用 `--body-draft <snapshot>=<path>` 提供完整 reference 草稿重新 plan；草稿中未受影响的段落由执行器原样保留，元数据和来源清单仍由执行器生成。
4. **确认。** 核对本次计划中的页面版本与审阅草稿依据的版本一致。若来源再次变化，先运行 `abort`，重审后重新 plan。展示差异和来源，按共享协议用 `action_id` 调用 `confirm_gate`。只有 `approved` 才进入下一步。取消、拒绝、工具缺失或失败时停止；若还未替换文件，运行 `abort` 清理事务。
5. **apply。** 运行 `scripts/refresh.py apply --action-id <编号>`。执行器在事务锁内重新计算现场哈希，门禁校验通过后才逐个以同目录 rename 原子替换 reference，每个替换前后都重新读取校验。两个 reference 都替换并复核成功后才删除事务标记；清理失败时如实报告“刷新已写入但事务清理未完成”。任一步失败保留事务标记，按异常恢复一节处理，不得静默接受半更新状态。
6. **报告。** 列出三个页面的来源版本和更新时间，以及两个快照各自的 `checked_at`、`checked_by`、正文差异和草稿使用情况。正文无差异时说明这次更新的是核对元数据。

## 异常恢复

- 页面读取、校验、候选写入或动作登记失败：原有快照不变；执行器删除本次临时文件和事务标记。
- 确认门禁不可用、报错或未放行：停止并报告，不改用自然语言确认，也不把工具错误记作用户拒绝；用户拒绝时运行 `abort` 清理事务。
- `confirm_gate` 不在可用工具列表中：确认无法展示给用户。停止并报告本 skill 需要带确认门禁的宿主，原有 reference 保持不变。
- 进程中断导致 `.refresh.pending` 残留：先运行 `status` 子命令。标记记录了每个目标替换前和候选的 SHA-256，与当前文件逐一比对即可判定哪些已被替换。两个 reference 都在 git 管理下：用 `git diff` 查看半更新状态，需要回滚已替换文件时用 `git checkout -- <reference>`。恢复（回滚或补完另一半替换）是明确的人工维护动作，业务 skill 不参与；处置完成后删除标记和残留临时文件，再重新调用本 skill，不得在未检查标记前直接重跑。`abort` 只在现场哈希证明两个 reference 都未被替换时才清理事务；已发生替换时它拒绝清理并指向本节。
- 刷新失败但旧快照存在：业务 skill 继续按原样读取本地快照，不校验版本或是否过期，也不要求用户接受旧快照。快照缺失或不可读时，业务 skill 无法应用规则。

本 skill 不执行 `git add`、`git commit`、`git push` 或 Redmine issue 更新。在线 Wiki 是刷新时的来源，本地快照是两个业务 skill 执行时的唯一规则来源。
