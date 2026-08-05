# Nationalchip Gerrit Patch Rules

## 来源与快照元数据
- 项目：`BU1-SDK-2007-01-UNIFY`
- 项目标识：`bu1-sdk`
- 在线来源由 [refresh-bu1-sdk-rules](../../refresh-bu1-sdk-rules/SKILL.md) 统一读取和维护；本文件是 `commit-bu1-sdk-gerrit` 执行时唯一使用的规则来源。
- `source_version: Gerrit使用规则=12; Gerrit补丁生成细则=9`
- `source_updated_on: Gerrit使用规则=2022-05-16T11:19:49Z; Gerrit补丁生成细则=2023-08-23T10:58:16Z`
- `checked_at: INVALID_UNTIL_REFRESH`
- `checked_by: UNKNOWN_UNTIL_REFRESH`
- `checked_at` 必须由刷新 skill 在成功核对在线页面后写入 UTC ISO 8601 时间；30 天期限只根据 `checked_at` 判断。当前快照缺少可信核对时间，业务 skill 必须先要求刷新。
- 在线 Wiki 与本地内容的差异只由刷新 skill 展示和处理；本业务 skill 不访问在线 Wiki、不刷新规则、不修改本文件。

当前快照整理自以下 Redmine REST Wiki API 页面：
- `GET https://git.nationalchip.com/redmine/projects/bu1-sdk/wiki/Gerrit%E4%BD%BF%E7%94%A8%E8%A7%84%E5%88%99.json`：页面 `Gerrit使用规则`，快照来源 version `12`，`updated_on` 为 `2022-05-16T11:19:49Z`。
- `GET https://git.nationalchip.com/redmine/projects/bu1-sdk/wiki/Gerrit%E8%A1%A5%E4%B8%81%E7%94%9F%E6%88%90%E7%BB%86%E5%88%99.json`：页面 `Gerrit补丁生成细则`，快照来源 version `9`，`updated_on` 为 `2023-08-23T10:58:16Z`。
- API 返回正文位于 `wiki_page.text`，读取和刷新遵守现有 **Redmine** skill 的认证与秘密处理要求。

## 公版 Gerrit 流程

Wiki 描述的流程是：

1. 解决一个 Redmine 任务并上传代码到 Gerrit。
2. 提交者自行检查代码格式和功能；确认没有补丁依赖后进行自 Review+1。
3. 如需他人评审，将必要人员加入 Reviewers 列表。
4. 提交者 Review+1 后触发 Jenkins Review；Jenkins Review+1 后进入人工 Review 阶段。
5. Reviewer 全部 Review+1 后，由补丁代码合并者根据公版需求选择是否合并。

本 skill 只负责创建 Gerrit 审核补丁，不自动执行 Gerrit 页面上的 Review+1、添加 Reviewer 或合并操作。

## 补丁代码提交者要求

提交者必须遵守以下要求：

- 按本文件的补丁生成规则提交补丁到 Gerrit。
- 提交代码前至少确认：遵守代码规范、没有多余代码、没有多余文件，并且自测功能正常。
- 提交补丁后，还要使用干净版本打上该补丁，进行补丁功能完整性测试。
- 如果需要他人 Review，或需要他人验证代码有效性，只加入必要的 Reviewer，不为数量而增加人员。
- 提交者完成自 Review 后，确认补丁没有问题且需要合并时，进行 Review+1。
- 如果补丁依赖平台补丁或其他补丁，等被依赖补丁合并到主线分支 `sdk-release` 后，再进行 Review+1。
- 收到其他 Reviewer 的 Review-1 后，根据意见修改整理，并在原有提交补丁上盖楼，重新走 Review 流程。

### 测试时序

“提交前自测”和“提交后在干净版本上打补丁测试”是两个不同检查：

- 提交前：必须确认当前工作树代码自测结果。
- 提交后：必须在干净版本上应用刚创建的补丁并完成完整功能测试。

skill 可以在 push 成功后报告第二项测试尚待完成，但不得把它写成已经完成，也不得把未提供的测试结果当成通过。

## 补丁提交格式

完整提交消息结构为：

```text
Type: [Redmine ID]: [Subject]

Body

Footer
```

Body 和 Footer 都是可选的；如果存在，Subject、Body、Footer 之间按上面的空行分隔。

### Type

只能根据修改内容选择以下类型：

- `feat`: 增加新功能
- `fix`: 修复错误
- `docs`: 修改文档
- `style`: 修改样式、空格、格式缩进、逗号等，不改变代码逻辑
- `refactor`: 代码重构
- `test`: 增加测试模块，不涉及生产环境代码
- `chore`: 更新核心模块、配置文件、构建流程、依赖库、工具等，不涉及生产环境代码

无法在多个 Type 中可靠选择时，列出候选并询问用户，不自行决定。

### Redmine ID

- 使用关联任务的 Redmine 问题号。
- Redmine 问题必须真实存在并可由当前凭据访问。
- 针对公版项目，必须关联 Unify 项目的 Redmine 记录；无法判断当前仓库是否属于公版项目，或问题不属于要求的 Unify 项目时，询问用户。

### Subject

- 不超过 50 个字符。
- Subject 的主体必须使用简体中文，使用祈使句描述修改内容，并以中文动词开头。
- 缩写、产品名、模块名、协议名、API 名、命令名等专有名词可以保留英文；除这些必要术语外，不使用普通英文单词组成标题。
- 不生成全英文 Subject，也不使用普通英文动词开头的英文句子。
- 描述必须简洁准确地反映实际补丁修改，不能直接照搬 Redmine 标题，除非 Redmine 标题本身已经符合补丁描述要求。
- 结尾不加句号 `.` 或中文句号 `。`。
### Body

- 不强制要求添加；内容也可以写在 Redmine 任务结论中。
- 如果添加，正文每行不超过 72 个字符。
- 只写已从实际变更或用户明确提供的信息中确认的内容。

### Footer

- Footer 可选，通常用于补充错误信息 ID 等信息。
- Gerrit 所需的 `Change-Id` 应由仓库 `commit-msg` hook 生成；skill 不手工伪造它。

## 提交描述和范围

- 必须有对应的 Redmine 记录，并且补丁要关联到对应 Redmine。
- 上传信息中的补丁描述要简洁、准确并符合实际修改，不能只是简单引用 Redmine 任务标题。
- 当前 skill 默认将当前 Git 仓库的修改作为补丁范围；用户明确指定范围时，只处理指定内容。

## 执行解释

以下是 skill 的执行门槛，不是对 Wiki 原文的扩展：

- 在展示完整 commit message 草稿并得到用户明确确认前，不执行本次流程的 `git add`、`git commit` 或 `git push`。
- 在 commit 前验证提交消息符合本文件的格式，并验证 `commit-msg` hook 生成合法 `Change-Id`。
- push 成功后必须单独报告干净版本补丁测试和 Review+1 的状态；未知状态保持未知。
- 规则不明确、依赖状态不明、提交者角色不明或公版/Unify 项目关系不明时，先询问用户。提交前自测由用户保证，不要求用户提供测试输出，也不因缺少自测证据停止。
