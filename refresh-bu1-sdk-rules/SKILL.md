---
name: refresh-bu1-sdk-rules
description: Refresh the local BU1-SDK Gerrit and Redmine rule snapshots from authenticated Redmine Wiki APIs, show rule changes, and update both snapshots only after explicit confirmation.
disable-model-invocation: true
---

# Refresh BU1-SDK Rules

这是唯一负责在线读取并维护 BU1-SDK 本地规则快照的 skill。`commit-gerrit` 和 `update-issue-conclusion` 在业务执行期间只读取本地快照，不访问在线 Wiki，不修改 reference 文件，也不检查快照版本、是否过期或刷新事务。需要更新时由用户手动调用本 skill。

## 规则来源

使用可用的 **Redmine** skill 完成认证、API 调用、TLS、XSSI 和秘密处理。不得输出 API key、Authorization header、netrc 内容或完整认证响应。

必须读取以下三个 API 页面，并从每个响应的 `wiki_page` 中取得 `text`、`version` 和 `updated_on`：
- `GET /projects/bu1-sdk/wiki/Gerrit%E4%BD%BF%E7%94%A8%E8%A7%84%E5%88%99.json`
- `GET /projects/bu1-sdk/wiki/Gerrit%E8%A1%A5%E4%B8%81%E7%94%9F%E6%88%90%E7%BB%86%E5%88%99.json`
- `GET /projects/bu1-sdk/wiki/Redmine%E4%BD%BF%E7%94%A8%E8%A7%84%E5%88%99.json`

一次刷新必须完整成功读取这三个页面。前两个页面的规则共同组成 `commit-gerrit` 的快照，第三个页面组成 `update-issue-conclusion` 的快照。刷新时应保留本地 reference 的规则摘录结构，并同步每个来源页面的版本、更新时间和核对元数据；不要把 API key 或原始认证响应写入文件。

## 刷新流程

1. **确认用户意图。** 该 skill 只在用户明确要求刷新规则，或由用户明确配置的外部调度器调用时运行。skill 不依赖模型自唤醒实现定时器。展示当前本地快照版本和 `checked_at`；外部调度器也必须保留本 skill 的确认和失败策略。开始前先确认 `ask_user_question` 出现在当前可用工具列表中：没有交互 UI 的宿主会把该工具整个从工具列表摘除，调度运行同样如此。工具不可用时立即停止并报告本 skill 需要交互式宿主，不创建事务标记、不写入 staging、不读取在线页面、不修改任何 reference，也不得改用自然语言确认。
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
6. **使用 ask_user_question 等待明确确认。** 候选快照和差异展示完毕后，不要只输出文字提示并等待自然语言回复；调用 `ask_user_question` 工具展示一个单选确认框：
   ```json
   {
     "questions": [
       {
         "header": "刷新确认",
         "question": "是否用本次读取到的两个候选快照替换本地规则快照？",
         "options": [
           {
             "label": "确认刷新规则",
             "description": "接受本次两个候选快照（包括核对元数据）并继续原子替换。"
           },
           {
             "label": "保留现有快照",
             "description": "不替换任何 reference；删除本次 staging 和事务标记，原有快照保持不变。"
           }
         ]
       }
     ]
   }
   ```
   `保留现有快照` 是显式的拒绝选项：它是记录得下的用户决定；`Esc` 由工具本身处理并返回 `details.cancelled: true`，是中断通道而不是拒绝。两者都不写入 reference，但最终报告必须区分二者。本次调用只有一个问题，`questionIndex` 恒为 `0`，不具区分力；按 `answers[].question` 与本次发出的 `question` 文本精确相等定位条目，且只接受本次调用返回的结果，丢弃更早调用的结果。

   **先判 `details.error`。** 工具的所有错误返回都同时带 `cancelled: true` 和空的 `answers` 数组，因此错误永远不是用户决定，不得当作用户取消或拒绝上报，也绝不能原样重发同一个调用——同样的调用只会复现同样的错误，而对话框根本没有渲染，用户连 `Esc` 都按不了。
   - 作者错误（`reserved_label`、`duplicate_option_label`、`empty_options`、`too_many_questions`、`duplicate_question`）说明本 skill 构造了非法问题：修正问题本身（改掉冲突的 `label`、修正选项数量）后发出修正过的调用；连续 2 次修正仍失败就停止并报告，删除本次 staging 和事务标记，原有 reference 保持不变。
   - 宿主错误（`no_ui`、`no_custom_ui`、`session_load_failed`、`stale_module_cache`）说明问题根本没有展示给用户：停止并报告本 skill 需要交互式宿主，删除本次 staging 和事务标记，原有 reference 保持不变。不得声称用户取消，不得改用自然语言确认，也不得继续替换。

   **`details.error` 不存在时。** 只把 `details.cancelled` 为 `false`、且 `details.answers` 中存在 `question` 恰好等于本次 `question` 文本、`kind` 恰好为 `option`、`answer` 恰好等于 `确认刷新规则` 的条目视为明确确认。`保留现有快照`、`details.cancelled: true`、缺少该条目、`kind` 为 `custom`（用户自己敲入的自由文本，永不构成授权）、`answer` 与选项标签不符，都不得写入 reference。用户可以只提交一个全局备注、一个选项都不选，此时 `details.cancelled` 仍为 `false` 且工具返回的散文仍读作“已回答”；因此绝不能凭散文文本或“未取消”判断，必须按上述条件校验 `answers` 条目。`details.globalNote` 和 `answers[].notes` 只是上下文，永远不构成确认。每个问题都会自动追加一行 `Type something.` 且无法关闭，自由文本始终可达但永不授权。不要使用 `qna` 扩展生成的 Q&A 汇总，也不要把工具之外的“好的”“确认”等模糊自然语言回复当作确认。用户选择 `保留现有快照`、按 `Esc` 取消、要求修改规则内容、只更新其中一个页面或拒绝刷新时，删除 staging 和事务标记，原文件保持不变；结果无效（缺少条目、`kind` 为 `custom`、`answer` 与本次发出的选项标签不符）时原样重新调用同一个 `ask_user_question`。记录匹配到的 `question`、`answer` 标签和 `header`，不记录凭据。
7. **完整校验后替换。** 确认后再次校验两个候选文件都存在、元数据完整、内容非空且 staging 路径属于本次事务。将两个候选文件分别复制为各自目标 reference 所在目录中的临时文件，临时文件名必须包含本次事务 ID；分别校验临时文件内容和 hash 与候选一致。两个临时文件都校验成功后，再分别使用原子 rename 替换两个 reference。两次 rename 不是跨文件整体原子操作，因此必须保留事务标记，直到两个 reference 都替换成功且重新读取校验通过。任一临时文件复制、校验、rename 或最终复核失败，都必须停止并报告，不得声称刷新完成；若只完成了一个 rename，保留事务标记，按事务记录和 hash 进行人工恢复，不得静默接受半更新状态。
8. **清理并报告。** 只有两个 reference 都替换成功且重新读取校验通过后，才删除 staging 和 `.refresh.pending`。最终报告两个页面的 source version、source updated time、checked_at、checked_by 和是否存在规则差异。清理失败时报告“刷新已写入但事务清理未完成”；业务 skill 不会因事务标记停止，但用户应完成清理后再重新调用本 skill。

## 异常恢复

- 页面读取、校验、差异确认或写入失败：原有快照不变；能安全清理时删除本次 staging 和标记。
- `ask_user_question` 不在可用工具列表中，或返回 `no_ui`/`no_custom_ui`/`session_load_failed`/`stale_module_cache`：确认闸门无法展示给用户，停止并报告本 skill 需要交互式宿主；删除本次 staging 和事务标记，原有快照保持不变。不得改用自然语言确认，不得把这种情况记作用户取消或拒绝。
- 进程中断导致 `.refresh.pending` 保留：业务 skill 不会因此停止。用户应检查标记中的 staging 路径和候选 hash，确认没有写入 reference 后删除 staging 和标记，再重新调用本 skill；不得直接删除未检查的标记。
- 发现两个 reference 只有一个已替换：保留事务标记，比较两份文件的元数据和 hash；恢复到替换前快照或完成另一份替换都必须是明确的人工维护动作，业务 skill 不参与恢复。
- 刷新失败但旧快照存在：业务 skill 继续按原样读取本地快照，不校验版本或是否过期，也不要求用户接受旧快照。快照缺失或不可读时，业务 skill 无法应用规则。

本 skill 不执行 `git add`、`git commit`、`git push` 或 Redmine issue 更新。在线 Wiki 是刷新时的来源，本地快照是两个业务 skill 执行时的唯一规则来源。
