---
name: refresh-bu1-sdk-rules
description: Refresh the local BU1-SDK Gerrit and Redmine rule snapshots from authenticated Redmine Wiki APIs, show rule changes, and update both snapshots only after explicit confirmation.
disable-model-invocation: true
---

# Refresh BU1-SDK Rules

这是唯一负责在线读取并维护 BU1-SDK 本地规则快照的 skill。`commit-bu1-sdk-gerrit` 和 `update-bu1-sdk-issue-conclusion` 在业务执行期间只读取本地快照，不访问在线 Wiki，也不修改 reference 文件。

## 规则来源

使用可用的 **Redmine** skill 完成认证、API 调用、TLS、XSSI 和秘密处理。不得输出 API key、Authorization header、netrc 内容或完整认证响应。

必须读取以下三个 API 页面，并从每个响应的 `wiki_page` 中取得 `text`、`version` 和 `updated_on`：
- `GET /projects/bu1-sdk/wiki/Gerrit%E4%BD%BF%E7%94%A8%E8%A7%84%E5%88%99.json`
- `GET /projects/bu1-sdk/wiki/Gerrit%E8%A1%A5%E4%B8%81%E7%94%9F%E6%88%90%E7%BB%86%E5%88%99.json`
- `GET /projects/bu1-sdk/wiki/Redmine%E4%BD%BF%E7%94%A8%E8%A7%84%E5%88%99.json`

一次刷新必须完整成功读取这三个页面。前两个页面的规则共同组成 `commit-bu1-sdk-gerrit` 的快照，第三个页面组成 `update-bu1-sdk-issue-conclusion` 的快照。刷新时应保留本地 reference 的规则摘录结构，并同步每个来源页面的版本、更新时间和核对元数据；不要把 API key 或原始认证响应写入文件。

## 刷新流程

1. **确认用户意图。** 该 skill 只在用户明确要求刷新规则，或由用户明确配置的外部调度器调用时运行。skill 不依赖模型自唤醒实现定时器。展示当前本地快照版本和 `checked_at`；外部调度器也必须保留本 skill 的确认和失败策略。
2. **检查刷新事务。** 以 `refresh-bu1-sdk-rules/.refresh.pending` 作为事务标记。若标记已经存在，停止并要求用户先检查上一次刷新留下的 staging 内容；不得覆盖、删除或猜测恢复。开始刷新前创建该标记，并在其中只记录事务 ID、开始时间和 staging 路径，不记录凭据。
3. **读取全部页面。** 一次刷新必须成功读取并基本校验所需的全部 Wiki API 页面：HTTP/API 成功、`wiki_page.text` 非空、`version` 是正整数、`updated_on` 是可解析的 UTC 时间。任一页面失败时删除本次 staging 内容和事务标记，保留所有原有 reference，并报告失败原因。
4. **生成候选快照。** 在 `refresh-bu1-sdk-rules/.staging/<transaction-id>/` 写入两个候选 reference。候选文件必须保留原有规则内容，并包含以下元数据：

   ```text
   source_version: <每个来源页面的 name=version 映射；Gerrit 快照记录两个页面>
   source_updated_on: <每个来源页面的 name=updated_on 映射>
   checked_at: <当前 UTC ISO 8601 时间>
   checked_by: <当前执行者标识>
   ```

   `checked_at` 是本次成功读取并核对在线页面的时间，不能用文件 mtime 或 `source_updated_on` 代替。
5. **比较并展示差异。** 将候选快照与两个本地 reference 分别比较。展示来源版本、核对时间和规则正文的摘要差异；不得展示凭据。即使规则正文没有差异，也要说明只会更新核对元数据。
6. **等待明确确认。** 只接受针对本次两个候选快照的明确确认，例如 `确认刷新规则`。发现任何规则差异时，未经确认不得替换本地快照。用户要求修改规则内容、只更新其中一个页面或拒绝刷新时，删除 staging 和事务标记，原文件保持不变。
7. **完整校验后替换。** 确认后再次校验两个候选文件都存在、元数据完整、内容非空且 staging 路径属于本次事务。然后按以下顺序操作：先将两个候选文件分别复制到同一目录下的临时目标文件，校验临时目标内容和 hash 与候选一致，再用原子 rename 替换两个 reference。任何一步失败都停止并报告；不要声称刷新完成。若系统无法保证两个 rename 的整体原子性，应保留事务标记并要求人工按 hash 比对后恢复，不得静默接受半更新状态。
8. **清理并报告。** 只有两个 reference 都替换成功且重新读取校验通过后，才删除 staging 和 `.refresh.pending`。最终报告两个页面的 source version、source updated time、checked_at、checked_by 和是否存在规则差异。清理失败时报告“刷新已写入但事务清理未完成”，业务 skill 会因事务标记停止。

## 异常恢复

- 页面读取、校验、差异确认或写入失败：原有快照不变；能安全清理时删除本次 staging 和标记。
- 进程中断导致 `.refresh.pending` 保留：后续业务 skill 必须停止。用户应检查标记中的 staging 路径和候选 hash，确认没有写入 reference 后删除 staging 和标记，再重新调用本 skill；不得直接删除未检查的标记。
- 发现两个 reference 只有一个已替换：保留事务标记，比较两份文件的元数据和 hash；恢复到替换前快照或完成另一份替换都必须是明确的人工维护动作，业务 skill 不参与恢复。
- 刷新失败但旧快照存在：业务 skill 可以在用户明确接受的前提下继续使用旧快照，并披露其 `checked_at`；旧快照不存在或元数据无效时，业务 skill 必须停止。

本 skill 不执行 `git add`、`git commit`、`git push` 或 Redmine issue 更新。在线 Wiki 是刷新时的来源，本地快照是两个业务 skill 执行时的唯一规则来源。
