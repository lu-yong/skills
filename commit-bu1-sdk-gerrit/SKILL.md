---
name: commit-bu1-sdk-gerrit
description: Submit BU1-SDK changes as a Nationalchip Gerrit review, using the local BU1-SDK patch-rule snapshot and requiring a valid issue number, a confirmed commit draft, an amend choice, and a verified target branch before pushing.
disable-model-invocation: true
---

# Commit BU1-SDK Gerrit

这是一个有副作用的用户主动调用 skill。它只用于向公司 Gerrit 创建审核补丁；不要因为普通的 commit、push 或 Gerrit 查询请求自动调用它。先完成检查和草稿，再按用户确认逐步执行。

## 不可变前置条件

- 必须要求用户提供一个 Redmine 问题号。只接受匹配 `^[1-9][0-9]*$` 的单个正整数；拒绝 URL、`#123`、范围、逗号分隔值、带前后其他文字的值和非十进制 ID。
- 使用可用的 **Redmine** skill 读取 `https://git.nationalchip.com/redmine/issues/<id>.json`，确认该问题存在、当前凭据可访问，并且 `issue.project.identifier` 精确等于 `bu1-sdk`；项目标识缺失或不匹配时停止。记录问题号、项目标识、标题、跟踪类型和状态；无法访问或问题不存在时停止并询问用户。
- 业务规则唯一来自本 skill 的本地快照 [references/bu1-sdk-gerrit-rules.md](references/bu1-sdk-gerrit-rules.md)，在生成草稿前完整阅读。运行过程中不访问在线 Wiki，不刷新在线规则，也不写入或静默修改任何 reference 文件。
- 规则快照的在线来源和版本元数据保留在 reference 中；需要检查或更新快照时，停止当前业务流程并请用户单独调用 [refresh-bu1-sdk-rules](../refresh-bu1-sdk-rules/SKILL.md)。刷新 skill 的结果不会由本 skill 自动接受或覆盖。
- 开始规则检查时确认 reference 存在、可读，并按 reference 的来源与快照元数据 节校验元数据（`source_version`、`source_updated_on`、`checked_at`、`checked_by` 存在，`checked_at` 为可解析 UTC ISO 8601；30 天期限只按该节规则以 `checked_at` 计算）。缺失、无效或过期时停止，要求先维护快照；只有用户明确回复本次使用旧快照才可继续，并在草稿和最终报告中披露“使用已过期本地快照”。
- 如果存在刷新事务标记 `refresh-bu1-sdk-rules/.refresh.pending`，停止并等待刷新事务完成或回滚；不读取在线内容、不自行修复标记。
- 当前 Git 仓库的修改内容默认为本次提交内容，包括已暂存、未暂存和未被忽略的未跟踪文件。只有用户明确指定文件、路径、补丁或范围时，才使用指定范围。
- 本地工作分支必须先通过“阶段零：本地工作分支硬门槛”：不能是 detached HEAD、`main`、`master`、`develop`、`sdk-release` 或与 Gerrit 目标分支同名，且必须配置有效目标分支。检查失败时立即结束 skill，要求用户创建并切换本地工作分支后重新调用。
- 推送前必须确认当前分支配置了非空的 `branch.<local_branch>.merge`，并且该目标分支已在推送远端创建。缺少配置或远端分支检查失败时停止，不自行创建、改名或猜测目标分支。
- Gerrit 提交必须由仓库的 `commit-msg` hook 生成合法 `Change-Id`。找不到可执行 hook、hook 执行失败或最终提交缺少合法 `Change-Id: I<40位十六进制字符>` footer 时停止，不手工伪造 Change-Id。
- 不显示或写入 Redmine API key、Gerrit 密码、netrc 内容、Authorization header 或其他凭据。

## 阶段零：本地工作分支硬门槛

这是本 skill 的第一步，必须先于 Redmine 校验、变更分析和草稿生成执行。运行：

```bash
local_branch=$(git branch --show-current)
test -n "$local_branch" || { printf '%s\n' 'commit-bu1-sdk-gerrit 已停止：当前处于 detached HEAD，未创建或未切换到本地工作分支。请先创建并切换工作分支后重新调用 skill。' >&2; exit 1; }
dest_branch=$(git config --get "branch.$local_branch.merge" | sed 's#^refs/heads/##')
test -n "$dest_branch" || { printf '%s\n' 'commit-bu1-sdk-gerrit 已停止：当前本地分支没有配置 Gerrit 目标分支。请先创建并配置工作分支后重新调用 skill。' >&2; exit 1; }
case "$local_branch" in
  main|master|develop|sdk-release) printf '%s\n' 'commit-bu1-sdk-gerrit 已停止：当前分支是基础分支，不是本地工作分支。请先创建并切换 topic/work 分支后重新调用 skill。' >&2; exit 1 ;;
esac
test "$local_branch" != "$dest_branch" || { printf '%s\n' 'commit-bu1-sdk-gerrit 已停止：当前本地分支与 Gerrit 目标分支相同，不是独立工作分支。请先创建并切换工作分支后重新调用 skill。' >&2; exit 1; }
remote_name=$(git config --get "branch.$local_branch.remote")
test -n "$remote_name" || { printf '%s\n' 'commit-bu1-sdk-gerrit 已停止：当前分支没有配置 branch.<local_branch>.remote。请先配置工作分支对应的 push remote 后重新调用 skill。' >&2; exit 1; }
pushurl_count=$(git config --get-all "remote.$remote_name.pushurl" | wc -l | tr -d ' ')
if [ "$pushurl_count" -gt 1 ]; then printf '%s\n' 'commit-bu1-sdk-gerrit 已停止：当前分支对应 remote 配置了多个 pushurl，无法唯一确定推送目标。请先处理 remote 配置后重新调用 skill。' >&2; exit 1; fi
if [ "$pushurl_count" -eq 1 ]; then
  push_url=$(git config --get "remote.$remote_name.pushurl")
else
  url_count=$(git config --get-all "remote.$remote_name.url" | wc -l | tr -d ' ')
  test "$url_count" -eq 1 || { printf '%s\n' 'commit-bu1-sdk-gerrit 已停止：当前 remote 没有唯一 pushurl 或 url，无法确定推送目标。请先处理 remote 配置后重新调用 skill。' >&2; exit 1; }
  push_url=$(git config --get "remote.$remote_name.url")
fi
test -n "$push_url" || { printf '%s\n' 'commit-bu1-sdk-gerrit 已停止：当前 remote 的推送 URL 为空。请先配置 remote 后重新调用 skill。' >&2; exit 1; }
remote_host=$(printf '%s\n' "$push_url" | sed -E 's#^[^:]+://([^@/]+@)?([^/:]+).*#\2#; s#^[^@]+@([^:]+):.*#\1#')
case "$remote_host" in
  git.nationalchip.com|gerrit.nationalchip.com) ;;
  *) printf '%s\n' 'commit-bu1-sdk-gerrit 已停止：push URL host 不是允许的公司 Gerrit host。请先确认 remote 配置后重新调用 skill。' >&2; exit 1 ;;
esac
git ls-remote --exit-code --heads "$push_url" "refs/heads/$dest_branch" >/dev/null || { printf '%s\n' 'commit-bu1-sdk-gerrit 已停止：Gerrit 目标分支尚未创建或当前 push URL 无法访问。请先确认目标分支和 push URL 后重新调用 skill。' >&2; exit 1; }
confirmed_remote_name="$remote_name"
confirmed_push_url="$push_url"
confirmed_remote_host="$remote_host"
confirmed_dest_branch="$dest_branch"
printf '%s\n' '已固定本次流程目标：remote 名称、push URL、host 和目标 branch。后续阶段只能复核并使用这些已确认值。'
```

以上任一检查失败时，立即结束本次 skill 调用，不读取 Redmine、不分析 Git 修改、不生成 commit 草稿，也不执行任何 `git add`、`git commit` 或 `git push`。不要自动创建、切换、改名或修复分支。用户需要先完成本地工作分支创建/切换及目标分支配置，再重新调用 skill。

## 阶段一：检查并生成草稿

1. 先验证 Redmine 问题号并读取问题详情。问题号合法只表示格式正确；只有 API 成功返回问题详情且 `issue.project.identifier` 精确等于 `bu1-sdk` 才算“合法问题号”。项目标识缺失或不匹配时停止，不生成草稿。commit message 中使用的 Redmine ID 就是该已验证的问题号，不另行要求 Unify 关联。
2. 在继续规则分析前读取本地 reference，并按 不可变前置条件 的快照规则校验元数据、时效和刷新事务标记。
3. 解析仓库根目录并收集当前状态：
   - `git rev-parse --show-toplevel`
   - `git status --short`
   - `git branch --show-current`
   - 当前分支的 remote、merge 配置和 push URL。
   默认范围要列出所有会被提交的路径，包括删除、修改、新增和已暂存路径。对未跟踪文件读取必要内容以便检查是否是敏感文件、生成物或与问题无关的内容；不要把文件内容或凭据输出给用户。状态收集结果按「工作区快照固定格式」记录固定字段。
4. 以 `HEAD` 为基线检查完整变更：已暂存和未暂存变更使用 `git diff --binary HEAD`；未跟踪文件单独检查。按「工作区快照固定格式」生成并记录完整快照；快照只记录路径、类型、大小和 hash，不记录文件内容或凭据。如果用户明确指定了范围：
   - 先使用 NUL-safe 的 `git diff --cached --name-only -z` 读取调用 skill 前已经存在的 index 路径，并按完整路径集合与 `confirmed-paths` 比较；覆盖修改、新增、删除、重命名和带空格的路径。
   - 任何已有 staged 路径不属于确认范围时，立即停止，展示路径、当前范围和阻塞原因，要求用户明确扩大范围或自行处理；不要执行 `git restore --staged`，不要静默改变用户 index。
   - 没有范围外路径时，确认指定范围内每个路径都存在于快照中，并把范围、已有 staged 路径和本次待加入路径分别记录在草稿中。
5. 复核阶段零固定的工作分支目标：
   - 重新读取当前分支的 `branch.<local_branch>.remote`、该 remote 的唯一 `pushurl`（没有时使用唯一 `url`）、解析出的 host 和 `branch.<local_branch>.merge`。
   - 将这些当前值与阶段零保存的 `confirmed_remote_name`、`confirmed_push_url`、`confirmed_remote_host`、`confirmed_dest_branch` 逐项比较。
   - 任一值变化、缺失、出现多个候选或 host 不在白名单时，停止并重新生成草稿；不得重新选择另一个 remote。
   - 使用阶段零已确认的目标执行目标分支存在性检查：
   ```bash
   git ls-remote --exit-code --heads "$confirmed_push_url" "refs/heads/$confirmed_dest_branch" >/dev/null
   ```
   草稿展示 remote 名称、push URL（按秘密处理规则脱敏）、host、目标 branch 和一致性校验结果。
6. 检查仓库 hooks 路径：
   ```bash
   commit_msg_hook=$(git rev-parse --git-path hooks/commit-msg)
   test -x "$commit_msg_hook" || { printf '%s\n' '缺少可执行 commit-msg hook' >&2; exit 1; }
   ```
   如果仓库使用 `core.hooksPath`，以 Git 解析出的路径为准。
7. 完整读取并应用 [references/bu1-sdk-gerrit-rules.md](references/bu1-sdk-gerrit-rules.md)，按 补丁提交格式 节校验 `Type: [Redmine ID]: [Subject]` 结构、Type 枚举、Subject（不超过 50 字符、简体中文祈使、专有名词英文例外、无句号）、Body（每行 72 字符）、Footer 与 `Change-Id` 规则；Type 无法唯一确定时列出候选并询问用户。草稿标注使用的 `source_version`、`checked_at` 和 `checked_by`。
   - 完整 commit message 只能写入已确认事实；Subject 按 reference 的 Subject 规则生成，不直接照搬 Redmine 标题。
   - 提交者保证（代码规范、无多余代码/文件、自测）按 reference 的 补丁代码提交者要求 节执行，干净版本测试时序和 Review/依赖状态按 测试时序 和 执行解释 节执行：本 skill 不要求自测日志、命令或测试输出，也不因缺少自测证据停止；除非用户明确说明尚未自测或要求协助测试，否则将自测功能正常视为用户保证。自 Review+1、Reviewer 与依赖补丁状态未知时保持未知，不在草稿或最终报告中假设已完成；每项规则都要能指出本地规则引用或当前事实。
8. 生成提交消息草稿。草稿必须只使用已确认事实，且完整显示拟提交的 subject、body 和 footer；Redmine 问题号必须按已读取规则的精确格式关联。不要把本地路径、未验证的测试结果或猜测写成事实。
9. 向用户展示以下内容，然后停止等待明确确认：
   - Redmine 问题详情、已验证的 `issue.project.identifier == bu1-sdk` 和访问结果。
   - Git 仓库、当前工作分支、目标分支、push remote 和推送范围。
   - 变更文件清单及简短的事实性摘要。
   - 本地规则快照的来源页面、版本、`checked_at`、`checked_by`，以及是否使用了过期快照。
   - 固定字段快照摘要（`HEAD`、工作区与已暂存 diff hash、未跟踪文件 hash、分支/merge/remote/push URL/目标 branch、`commit-msg` hook 路径和 hash；不含文件内容、hook 内容和凭据）。
   - Gerrit 规则要求和仍待用户回答的问题（有任何一项就不要进入确认阶段）。
   - 完整的 commit message 草稿。
   - 明确声明：尚未执行本次流程的 `git add`、`git commit` 或 `git push`；已经存在的用户暂存状态如有则如实说明。
   - 请求明确回复 `确认提交`。仅“好的”“看起来可以”或未回答所有问题不算确认。

## 工作区快照固定格式

阶段一生成一次固定字段快照并记录在草稿中；阶段二在 `git add` 前按同一格式重新生成，逐字段比较。任一字段变化都使阶段一的确认失效，回到重新生成草稿并再次请求确认。

固定字段与生成方式：

| 字段 | 生成方式 |
| --- | --- |
| `HEAD` SHA | `git rev-parse HEAD` 的完整 40 位 SHA |
| 工作区变更 hash | `git diff --binary HEAD` 输出的 SHA-256 |
| 已暂存变更 hash | `git diff --cached --binary` 输出的 SHA-256 |
| 未跟踪文件 hash | `git ls-files --others --exclude-standard -z` 列出的每个路径，按 `路径|类型|大小|内容SHA-256` 记录一行，按路径排序后整体再取一次 SHA-256 |
| 当前分支 | `git branch --show-current` |
| merge 配置 | `git config --get branch.<local_branch>.merge` 规范化后的值 |
| remote 名称 | `git config --get branch.<local_branch>.remote` |
| push URL | 阶段零确认的唯一 `pushurl`（无 `pushurl` 时用唯一 `url`） |
| 目标 branch | `branch.<local_branch>.merge` 去掉 `refs/heads/` 前缀后的值 |
| hook 路径 | `git rev-parse --git-path hooks/commit-msg`（使用 `core.hooksPath` 时以 Git 解析结果为准） |
| hook hash | `commit-msg` hook 文件的 SHA-256 |

生成示例（SHA-256 命令 macOS 用 `shasum -a 256`，Linux 用 `sha256sum`）：

```bash
git rev-parse HEAD
git diff --binary HEAD | shasum -a 256
git diff --cached --binary | shasum -a 256
git ls-files --others --exclude-standard -z | while IFS= read -r -d '' f; do
  [ -L "$f" ] && t=symlink || t=file
  printf '%s|%s|%s|%s\n' "$f" "$t" "$(wc -c < "$f" | tr -d ' ')" "$(shasum -a 256 "$f" | cut -d' ' -f1)"
done | sort | shasum -a 256
```

规则：

- 快照只记录路径、类型、大小和 hash，不记录也不输出未跟踪文件内容、diff 内容、hook 内容、凭据或任何秘密；文件名不变但内容、`HEAD`、remote、hook 或未跟踪文件变化时，对应 hash 或字段值会不同，必须能被发现。
- 未跟踪文件逐行记录 `路径|类型|大小|内容SHA-256`，按路径排序保证可比较；类型只用 `file`/`symlink`，大小为字节数。
- 阶段二在 `git add` 前重新生成全部字段并与阶段一逐项比较：任一字段缺失、无法生成或值不同，立即停止，重新执行阶段一生成新草稿，并再次请求明确确认；字段全部一致才允许继续 `git add`。

## 阶段二：用户确认后暂存

1. 只接受针对阶段一完整草稿的明确确认。若用户修改问题号、范围、消息或任何规则相关内容，重新执行受影响的检查并展示新草稿。
2. 在执行 `git add` 前按「工作区快照固定格式」重新生成全部快照字段，并与阶段一记录逐字段比较。任一字段变化（`HEAD`、工作区或已暂存 diff hash、未跟踪文件、分支、merge 配置、remote 名称、push URL、目标 branch、`commit-msg` hook 路径或 hash）都使阶段一确认失效：停止，重新执行阶段一生成新草稿并再次请求明确确认；不要把确认后新产生的修改静默纳入提交。
3. 确认快照未变化后才执行 `git add`：
   - 默认范围：在仓库根目录执行 `git add -A -- .`。
   - 用户指定范围：仅对确认过的路径执行 `git add -A -- <confirmed-paths>`，正确处理删除和带空格的路径。
4. 用 `git diff --cached --check`、`git diff --cached --stat`、NUL-safe 的 `git diff --cached --name-only -z` 和必要的 `git diff --cached` 复核暂存内容。用户指定范围时，暂存路径集合必须是 `confirmed-paths` 的子集；任一路径超出范围、规则不允许或校验失败，停止，不提交，不执行 `git restore --staged`。
5. 将实际暂存文件清单、暂存统计和仍存在的风险告知用户。此时仍不要执行 commit，并展示以下固定选项：
   1. `amend`
   2. `不amend`
   只接受用户单独输入 `1` 或 `2`；输入任何其他值都视为非法，必须再次展示这两个选项并询问。输入 `1` 映射为 amend，输入 `2` 映射为不 amend。

## 阶段三：amend 选择、提交和推送

1. 只接受阶段二选项中的单独输入 `1` 或 `2`：输入 `1` 时确认 `HEAD` 存在且用户理解这会改写当前最新提交，然后执行 amend；输入 `2` 时创建新提交。任何其他输入都是非法，重新展示选项并询问，不自行选择。选择 `1` 后，不得用阶段一为新提交生成的草稿直接覆盖 `HEAD` 的原有消息：先读取并记录 `HEAD` 的完整 commit message，将本次已确认 staged 变更的事实性摘要作为新段落追加到现有 Body。必须原样保留 `HEAD` 已有的 Subject、Body 和 Footer；摘要插入现有 Footer（包括 `Change-Id`）之前；没有 Footer 时才追加到消息末尾。无法可靠识别 Footer，或无法从实际变更中生成事实性摘要时，停止并询问。
2. 用临时文件保存最终 commit message：新提交使用阶段一已确认的完整草稿；amend 使用按上一步规则合成、并在 commit 前展示核对的消息，执行 `git commit --amend -F <temporary-message-file>`。设置 `GIT_EDITOR=true`，避免打开交互式编辑器；不要把临时文件放进仓库。提交失败时保留暂存区并报告错误，不推送。
3. 执行 commit 前再次使用 NUL-safe 的 `git diff --cached --name-only -z` 检查 staged 路径集合。用户指定范围时，任一路径不属于 `confirmed-paths` 都使流程停止；同时记录实际 staged 集合，供提交后比较实际 commit 范围。
4. 提交成功后验证：`git status --short`、`git show --stat --oneline HEAD`、`git diff-tree --no-commit-id --name-only -r HEAD -z`、完整 commit message、作者和 `Change-Id`。将实际 commit 路径集合与 commit 前记录的 staged 集合比较；若路径集合不一致、hook 改写了消息、没有合法 Change-Id 或提交结果与草稿不一致，停止推送并询问用户。
5. 提交成功且所有规则/前置条件复核通过后，使用阶段零已确认的 remote 和目标 branch 推送到 Gerrit 审核 ref；不重新读取或选择 remote，不改写为普通分支 push，不添加 `--force`：
   ```bash
   git push \
        --receive-pack='gerrit receive-pack' \
        --no-follow-tags \
        "$confirmed_remote_name" \
        "refs/heads/$local_branch:refs/for/$confirmed_dest_branch"
   ```
6. 只有 `git push` 返回成功才报告补丁已提交到 Gerrit 审核。最终报告包含 Redmine 问题号、提交 SHA、是否 amend、提交消息摘要、阶段零已确认的 `confirmed_remote_name`、`local_branch`、`confirmed_dest_branch` 和 Gerrit 审核 ref；推送失败时原样总结错误和下一步，不声称补丁已进入审核。
   - 单独报告“干净版本打补丁后的完整功能测试”和提交者自 Review+1 的状态；如果尚未完成或用户没有提供证据，标记为“待完成/未知”，不得写成通过。

## 停止条件

遇到凭据不可用、Redmine 问题号不存在、Redmine 项目标识缺失或不是 `bu1-sdk`、本地规则快照缺失或元数据无效、快照过期且用户未明确接受旧快照、刷新事务正在进行、规则冲突、阶段零本地工作分支硬门槛失败、提交者角色无法确认、分支/remote/目标分支无法确认、工作区快照任一固定字段在确认后变化、用户指定范围包含已有范围外 staged 路径、git add 后或 commit 前 staged 路径超出确认范围、范围包含未经确认的敏感或无关文件、commit-msg hook 缺失、消息不符合规则、Change-Id 缺失、commit 失败或 push 失败，都必须停在当前阶段并向用户说明具体原因。业务流程不得通过网络补齐规则，也不得自行改写 reference、取消用户已有暂存或扩大提交范围。阶段零失败时不得继续读取 Redmine、分析 Git 修改或生成 commit 草稿；用户创建并切换本地工作分支后重新调用 skill。任何不确定的规则或事实都先询问用户，不能用经验值补齐。
