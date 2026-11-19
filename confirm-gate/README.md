# 确认门禁

`commit-gerrit`、`update-issue-conclusion` 和 `refresh-bu1-sdk-rules` 用同一套确认凭据。业务脚本登记计划，宿主向用户显示计划，业务脚本在写入前重新校验现场状态并原子领取凭据。

## 在 pi 中启用

从本仓库根目录启动一次临时会话。把 `-e` 后的路径替换为绝对路径，就可以从目标项目中启动 pi。

```bash
pi -e "$PWD/confirm-gate/pi-extension/index.ts"
```

要让 pi 自动发现扩展，可以将本仓库的 `confirm-gate/pi-extension/` 目录链接到 `~/.pi/agent/extensions/confirm-gate`，然后重新启动 pi 或在交互会话运行 `/reload`。在目标项目中执行技能时，保留技能目录间的相对位置，例如将各技能目录链接到宿主的技能目录。

## 从计划到执行

1. 按业务技能执行计划命令，拿到 `action_id`。
2. 调用 `confirm_gate`，参数为 `{"action_id": "<计划返回的编号>"}`。用户在宿主 UI 中看到计划摘要和两个选项，默认光标落在取消项。
3. 只有工具返回 `approved` 时才调用该动作对应的执行命令。工具缺失、不可用、报错、取消或拒绝时停止并报告。取消、拒绝或 UI 失败会作废当前动作。需要继续时按业务技能重新生成计划并取得确认。

`ask_user_question` 用于实例、项目、分支或候选等结构化选择。两选一的写入授权由 `confirm_gate` 处理，执行凭据只在用户通过该工具确认后签发。

## 凭据与执行范围

Python 脚本与 pi 扩展使用同一状态目录。默认是 `$XDG_STATE_HOME/confirm-gate`，`XDG_STATE_HOME` 未设置时用 `~/.local/state/confirm-gate`。也可在启动宿主前把 `CONFIRM_GATE_STATE_DIR` 设为同一个绝对路径。动作自登记起有效 24 小时，确认凭据有效 10 分钟。重新提问前清除该动作的旧凭据。每张凭据只可领取一次，执行失败后也需再次确认。计划内容或现场状态变化时重新生成计划。

pi 的附加拦截只识别 `bash` 工具命令文本中字面匹配的 `git … push … refs/for/…`。业务脚本的子进程、用户自行运行的命令和其他宿主由其各自的执行环境管理。动作和凭据是同一 OS 用户可读写的本地文件，这个设计依赖该用户及其宿主进程可信。业务脚本负责实际的确认校验和消费。
