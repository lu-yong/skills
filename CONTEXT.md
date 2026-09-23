# Skills 仓库

一套跨宿主（pi、Codex、Claude Code、OpenCode 等）复用的 Agent 技能集合：每个目录一个技能，入口为该目录下的 `SKILL.md`，主要在 pi 中编写和调试。

## 提问交互

**门禁技能（gate skill）**:
答案会授权写操作或外部动作的技能。提问必须走宿主的结构化提问工具（`ask_user_question`），工具缺失或出错时停止并报告，不降级为自然语言确认。

**对话技能（conversation skill）**:
答案只影响对话走向、不授权任何写操作的技能。优先走结构化提问工具，工具缺失或出错时降级为 markdown 提问。
