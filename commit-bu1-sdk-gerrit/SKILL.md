---
name: commit-bu1-sdk-gerrit
description: Submit BU1-SDK changes as a Nationalchip Gerrit review, using the BU1-SDK Redmine-linked patch rules and requiring a valid issue number, a confirmed commit draft, an amend choice, and a verified target branch before pushing.
disable-model-invocation: true
---

# Commit BU1-SDK Gerrit

这是一个有副作用的用户主动调用 skill。它只用于向公司 Gerrit 创建审核补丁；不要因为普通的 commit、push 或 Gerrit 查询请求自动调用它。先完成检查和草稿，再按用户确认逐步执行。

## 不可变前置条件

- 必须要求用户提供一个 Redmine 问题号。只接受匹配 `^[1-9][0-9]*$` 的单个正整数；拒绝 URL、`#123`、范围、逗号分隔值、带前后其他文字的值和非十进制 ID。
- 使用可用的 **Redmine** skill 读取 `https://git.nationalchip.com/redmine/issues/<id>.json`，确认该问题存在且当前凭据可访问。记录问题号、项目标识、标题、跟踪类型和状态；无法访问或问题不存在时停止并询问用户。
- 读取并遵守本 skill 的本地规则引用 [references/bu1-sdk-gerrit-rules.md](references/bu1-sdk-gerrit-rules.md)，在生成草稿前完整阅读。该引用由 Redmine Wiki API 的 `wiki_page.text` 整理而成，不依赖运行时的网页登录态。
- 本地规则引用优先使用；用户明确要求刷新、报告规则变更、引用缺失或当前场景超出引用范围时，使用 **Redmine** skill 的认证读取这两个 Wiki API 页面：
  - `GET /projects/bu1-sdk/wiki/Gerrit%E4%BD%BF%E7%94%A8%E8%A7%84%E5%88%99.json`
  - `GET /projects/bu1-sdk/wiki/Gerrit%E8%A1%A5%E4%B8%81%E7%94%9F%E6%88%90%E7%BB%86%E5%88%99.json`
  读取 JSON 中的 `wiki_page.text`、`wiki_page.version` 和 `wiki_page.updated_on`；刷新成功后更新本地引用的规则和版本信息。读取 API key 时遵守 Redmine skill 的秘密处理要求，不打印 key 或完整认证响应。
- API 刷新失败但本地引用仍存在时，可以继续，但必须在草稿中披露使用的是本地快照；本地引用和 API 页面都不可用时停止并询问用户。所有来源都不可用，或来源之间对提交格式、角色要求、测试要求、依赖处理或 Redmine 关联方式存在冲突时，暂停并询问用户。
- 当前 Git 仓库的修改内容默认为本次提交内容，包括已暂存、未暂存和未被忽略的未跟踪文件。只有用户明确指定文件、路径、补丁或范围时，才使用指定范围。
- 本地工作分支必须先通过“阶段零：本地工作分支硬门槛”：不能是 detached HEAD、`main`、`master`、`develop`、`sdk-release` 或与 Gerrit 目标分支同名，且必须配置有效目标分支。检查失败时立即结束 skill，要求用户创建并切换本地工作分支后重新调用。
- 推送前必须确认当前分支配置了非空的 `branch.<local_branch>.merge`，并且该目标分支已在推送远端创建。缺少配置或远端分支检查失败时停止，不自行创建、改名或猜测目标分支。
- Gerrit 提交必须由仓库的 `commit-msg` hook 生成合法 `Change-Id`。找不到可执行 hook、hook 执行失败或最终提交缺少合法 `Change-Id: I<40位十六进制字符>` footer 时停止，不手工伪造 Change-Id。
- 不显示或写入 Redmine API key、Gerrit 密码、netrc 内容、Authorization header 或其他凭据。

## 阶段零：本地工作分支硬门槛

这是本 skill 的第一步，必须先于 Redmine 校验、Wiki API 刷新、变更分析和草稿生成执行。运行：

```bash
local_branch=$(git branch --show-current)
test -n "$local_branch" || { printf '%s\n' 'commit-bu1-sdk-gerrit 已停止：当前处于 detached HEAD，未创建或未切换到本地工作分支。请先创建并切换工作分支后重新调用 skill。' >&2; exit 1; }
dest_branch=$(git config --get "branch.$local_branch.merge" | sed 's#^refs/heads/##')
test -n "$dest_branch" || { printf '%s\n' 'commit-bu1-sdk-gerrit 已停止：当前本地分支没有配置 Gerrit 目标分支。请先创建并配置工作分支后重新调用 skill。' >&2; exit 1; }
case "$local_branch" in
  main|master|develop|sdk-release) printf '%s\n' 'commit-bu1-sdk-gerrit 已停止：当前分支是基础分支，不是本地工作分支。请先创建并切换 topic/work 分支后重新调用 skill。' >&2; exit 1 ;;
esac
test "$local_branch" != "$dest_branch" || { printf '%s\n' 'commit-bu1-sdk-gerrit 已停止：当前本地分支与 Gerrit 目标分支相同，不是独立工作分支。请先创建并切换 topic/work 分支后重新调用 skill。' >&2; exit 1; }
remote_name=$(git remote -v | awk '$3 == "(push)" {print $1; exit}')
test -n "$remote_name" || { printf '%s\n' 'commit-bu1-sdk-gerrit 已停止：没有可用的 Gerrit push remote。请先配置工作分支和 remote 后重新调用 skill。' >&2; exit 1; }
git ls-remote --exit-code --heads "$remote_name" "refs/heads/$dest_branch" >/dev/null || { printf '%s\n' 'commit-bu1-sdk-gerrit 已停止：Gerrit 目标分支尚未创建或当前 remote 无法访问。请先确认目标分支和 remote 后重新调用 skill。' >&2; exit 1; }
```

以上任一检查失败时，立即结束本次 skill 调用，不读取 Redmine 问题、不读取 Wiki、不分析 Git 修改、不生成 commit 草稿，也不执行任何 `git add`、`git commit` 或 `git push`。不要自动创建、切换、改名或修复分支。用户需要先完成本地工作分支创建/切换及目标分支配置，再重新调用 skill。

## 阶段一：检查并生成草稿

1. 先验证 Redmine 问题号并读取问题详情。问题号合法只表示格式正确；只有 API 成功返回问题详情才算“合法问题号”。
2. 解析仓库根目录并收集当前状态：
   - `git rev-parse --show-toplevel`
   - `git status --short`
   - `git branch --show-current`
   - 当前分支的 remote、merge 配置和 push URL。
   默认范围要列出所有会被提交的路径，包括删除、修改、新增和已暂存路径。对未跟踪文件读取必要内容以便检查是否是敏感文件、生成物或与问题无关的内容；不要把文件内容或凭据输出给用户。
3. 以 `HEAD` 为基线检查完整变更：已暂存和未暂存变更使用 `git diff --binary HEAD`；未跟踪文件单独检查。记录用于后续复核的工作区快照（状态、变更内容摘要和未跟踪文件 hash）。如果用户明确指定了范围，确认指定范围内每个路径都存在于快照中，并把范围显示在草稿里。
4. 检查工作分支和目标分支：
   ```bash
   local_branch=$(git branch --show-current)
   test -n "$local_branch" || { printf '%s\n' '当前处于 detached HEAD，无法提交 Gerrit' >&2; exit 1; }
   dest_branch=$(git config --get "branch.$local_branch.merge" | sed 's#^refs/heads/##')
   test -n "$dest_branch" || { printf '%s\n' '当前工作分支没有配置目标分支' >&2; exit 1; }
   remote_name=$(git remote -v | awk '$3 == "(push)" {print $1; exit}')
   test -n "$remote_name" || { printf '%s\n' '没有可用的 push remote' >&2; exit 1; }
   git ls-remote --exit-code --heads "$remote_name" "refs/heads/$dest_branch" >/dev/null
   ```
   同时确认 push URL 指向公司 Gerrit（通常是 `git.nationalchip.com` 或 `gerrit.nationalchip.com`）。远端主机、目标分支或 remote 有歧义时询问用户，不要将 GitHub 等其他 remote 当作公司 Gerrit。
5. 检查仓库 hooks 路径：
   ```bash
   commit_msg_hook=$(git rev-parse --git-path hooks/commit-msg)
   test -x "$commit_msg_hook" || { printf '%s\n' '缺少可执行 commit-msg hook' >&2; exit 1; }
   ```
   如果仓库使用 `core.hooksPath`，以 Git 解析出的路径为准。
6. 完整读取并应用 [references/bu1-sdk-gerrit-rules.md](references/bu1-sdk-gerrit-rules.md)：校验 `Type: [Redmine ID]: [Subject]` 结构、Type 值、Subject 不超过 50 个字符、Subject 主体为简体中文、祈使语气、专有名词英文例外、无句号规则、Body 每行 72 字符限制、Footer 可选性、Redmine 关联以及公版项目的 Unify 问题要求。
   - 根据实际变更选择唯一可靠的 Type；无法判断时列出候选并询问用户。Subject 必须简洁准确描述补丁，不直接照搬 Redmine 标题。完整 commit message 只能写入已确认事实。
   - 提交者对提交前的代码规范、无多余代码和无多余文件作出保证；本 skill 不要求用户提供自测日志、命令或测试输出，也不因缺少自测证据而停止。除非用户明确说明尚未自测或要求协助测试，否则将自测功能正常视为用户保证。
   - 记录提交后在干净版本上打补丁并进行完整功能测试、提交者自 Review+1、Reviewer 和依赖补丁的状态；这些状态未知时保持未知，不在草稿或最终报告中假设已完成。每项规则都要能指出本地规则引用或当前事实。
7. 生成提交消息草稿。草稿必须只使用已确认事实，且完整显示拟提交的 subject、body 和 footer；Redmine 问题号必须按已读取规则的精确格式关联。不要把本地路径、未验证的测试结果或猜测写成事实。
8. 向用户展示以下内容，然后停止等待明确确认：
   - Redmine 问题详情和访问结果。
   - Git 仓库、当前工作分支、目标分支、push remote 和推送范围。
   - 变更文件清单及简短的事实性摘要。
   - Gerrit 规则来源、已核对的要求和仍待用户回答的问题（有任何一项就不要进入确认阶段）。
   - 完整的 commit message 草稿。
   - 明确声明：尚未执行本次流程的 `git add`、`git commit` 或 `git push`；已经存在的用户暂存状态如有则如实说明。
   - 请求明确回复 `确认提交`。仅“好的”“看起来可以”或未回答所有问题不算确认。

## 阶段二：用户确认后暂存

1. 只接受针对阶段一完整草稿的明确确认。若用户修改问题号、范围、消息或任何规则相关内容，重新执行受影响的检查并展示新草稿。
2. 在执行 `git add` 前重新收集工作区快照并与阶段一比较。只要范围、文件状态或内容发生变化，就停止并重新生成草稿；不要把确认后新产生的修改静默纳入提交。
3. 确认快照未变化后才执行 `git add`：
   - 默认范围：在仓库根目录执行 `git add -A -- .`。
   - 用户指定范围：仅对确认过的路径执行 `git add -A -- <confirmed-paths>`，正确处理删除和带空格的路径。
4. 用 `git diff --cached --check`、`git diff --cached --stat`、`git diff --cached --name-status` 和必要的 `git diff --cached` 复核暂存内容。若暂存结果超出确认范围、规则不允许或校验失败，停止，不提交。
5. 将实际暂存文件清单、暂存统计和仍存在的风险告知用户。此时仍不要执行 commit，并展示以下固定选项：
   1. `amend`
   2. `不amend`
   只接受用户单独输入 `1` 或 `2`；输入任何其他值都视为非法，必须再次展示这两个选项并询问。输入 `1` 映射为 amend，输入 `2` 映射为不 amend。

## 阶段三：amend 选择、提交和推送

1. 只接受阶段二选项中的单独输入 `1` 或 `2`：输入 `1` 时确认 `HEAD` 存在且用户理解这会改写当前最新提交，然后执行 amend；输入 `2` 时创建新提交。任何其他输入都是非法，重新展示选项并询问，不自行选择。
2. 用临时文件保存已确认的完整 commit message，使用 `git commit -F <temporary-message-file>`；amend 使用 `git commit --amend -F <temporary-message-file>`。设置 `GIT_EDITOR=true`，避免打开交互式编辑器；不要把临时文件放进仓库。提交失败时保留暂存区并报告错误，不推送。
3. 提交成功后验证：`git status --short`、`git show --stat --oneline HEAD`、完整 commit message、作者和 `Change-Id`。若 hook 改写了消息，重新检查其是否仍满足 Gerrit 规则；若没有合法 Change-Id 或提交结果与草稿不一致，停止推送并询问用户。
4. 提交成功且所有规则/前置条件复核通过后，使用以下命令推送到 Gerrit 审核 ref，不改写为普通分支 push，不添加 `--force`：
   ```bash
   remote_name=$(git remote -v | awk '$3 == "(push)" {print $1; exit}')
   local_branch=$(git branch --show-current)
   dest_branch=$(git config --get "branch.$local_branch.merge" | sed 's#^refs/heads/##')

   git push \
        --receive-pack='gerrit receive-pack' \
        --no-follow-tags \
        "$remote_name" \
        "refs/heads/$local_branch:refs/for/$dest_branch"
   ```
5. 只有 `git push` 返回成功才报告补丁已提交到 Gerrit 审核。最终报告包含 Redmine 问题号、提交 SHA、是否 amend、提交消息摘要、实际 `remote_name`、`local_branch`、`dest_branch` 和 Gerrit 审核 ref；推送失败时原样总结错误和下一步，不声称补丁已进入审核。
   - 单独报告“干净版本打补丁后的完整功能测试”和提交者自 Review+1 的状态；如果尚未完成或用户没有提供证据，标记为“待完成/未知”，不得写成通过。

## 停止条件

遇到凭据不可用、Redmine 问题号不存在、本地规则引用缺失且在线规则不可读、规则冲突、阶段零本地工作分支硬门槛失败、提交者角色无法确认、公版/Unify 项目关系不明、分支/remote/目标分支无法确认、工作区在确认后变化、范围包含未经确认的敏感或无关文件、commit-msg hook 缺失、消息不符合规则、Change-Id 缺失、commit 失败或 push 失败，都必须停在当前阶段并向用户说明具体原因。阶段零失败时不得继续读取 Redmine、分析变更或生成草稿；用户创建并切换本地工作分支后重新调用 skill。提交前自测由用户保证，不因缺少测试证据停止。任何不确定的规则或事实都先询问用户，不能用经验值补齐。
