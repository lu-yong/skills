---
name: gerrit
description: Query Nationalchip Gerrit accounts, projects, changes, revisions, files, and patches. Use when a user refers to git.nationalchip.com/gerrit, git2.nationalchip.com/gerrit, gerrit.nationalchip.com, or wants to map a local commit to a Gerrit change.
---

# Gerrit 只读查询

用 `python3 "$SKILL_DIR/scripts/gerrit.py"` 查询，`SKILL_DIR` 指向本文件所在目录。CLI 依赖 Python 3 和 curl。命令失败时报告退出错误，遇到认证错误请用户检查凭据配置。

## 确定实例与凭据

先用 `instances` 查看实例名和配置。`internal` 使用 Digest，`git2` 和 `external` 使用 Basic。实例地址、认证方式、TLS 回退和推送主机统一登记在 [instances.json](instances.json)。

三个实例的变更编号各自独立。优先用用户提供的 URL 或实例名。关联本地提交时，`repo-context` 可从关联的 remote 取有效 push URL 并推断实例。遇到仅登记为推送目标的主机或无法确定实例时，请用户指定查询实例。

CLI 用 curl 读取 `GERRIT_NETRC_FILE` 或 `~/.netrc`，按目标主机选择机器条目。凭据文件权限设为 `600`，报告时只引用路径和错误，避免输出文件内容、密码或认证头。仅 `external` 在证书校验失败后会按登记回退，stderr 会提示。报告结果时保留该提示，并说明读到的实例和 revision。

## 查询命令

以下参数写在 `gerrit.py` 后面。显式指定 `--instance` 的例子使用 `internal`。

| 需要的信息 | 子命令 |
| --- | --- |
| 当前账号、项目或其他 GET 端点 | `get --instance internal /accounts/self`，项目端点用 `/projects/`，重复 `--param KEY=VALUE` 可过滤 |
| 变更详情 | `change --instance internal 127887`，也可用 `project~branch~Change-Id`，需要所有 patchset 时加 `--option ALL_REVISIONS` |
| 条件查询 | `query --instance internal 'project:goxceed/loader status:open' --all` |
| 改动文件 | `files --instance internal 127887 --revision current` |
| 补丁原文 | `patch --instance internal 127887 --revision current` |
| 本地仓库中的提交、项目和分支线索 | `repo-context` |
| 本地提交对应的变更 | `resolve-commit`，可显式传 `--sha`、`--change-id`、`--instance`、`--project`、`--branch` |

`query` 按页读取并返回 `complete`。用 `--limit` 控制返回数量，用 `--all` 扫描到结束（自动扫描上限 5,000 条）。只有 `complete: true` 的结果才可当作完整清单。`patch` 输出解码后的补丁原始字节，其余命令输出 JSON。

`resolve-commit` 用完整 SHA 和可用的 Change-Id 搜索，逐个获取候选详情与所有 patchset。再按 Change-Id、项目和目标分支筛选，优先采用精确 SHA 对应的 patchset。要求补充实例、项目或分支时按提示补齐。若返回多个候选，先给用户看各候选的变更号、项目、分支、状态和 exact SHA 匹配情况，经用户选择后加 `--pick <变更号>` 重查。访问失败或查询不完整时，报告无法核实的事实。
