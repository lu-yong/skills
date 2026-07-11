<!-- Source: install-openspec-superpowers-bridge/references/AGENTS.fragment.zh-TW.md -->
<!-- BEGIN OPENSPEC SUPERPOWERS BRIDGE -->
## 工作流路由

本倉庫使用 [`superpowers-bridge`](https://github.com/JiangWay/openspec-schemas/tree/main/superpowers-bridge) 串接 OpenSpec 與 Superpowers。artifact 規則以 bridge README 為準，這一節只處理代理路由。

### 入口分流

- 使用者先發起敘述式設計討論或腦力激盪：先討論，但不要把內容寫到 `docs/superpowers/specs/`。當範圍、關鍵決策、跨系統依賴、驗收條件、對話收斂都明確後，再建議 `/opsx:propose`。
- 使用者直接執行 `/opsx:new`、`/opsx:ff` 或 `/opsx:propose`：照 schema 流程執行。
- 使用者明確表示是 bug fix、typo、小型設定調整、純文件變更：直接 PR，不要開 change。
- 已經處於某個 change 中：繼續用 `/opsx:continue`、`/opsx:apply`、`/opsx:verify` 或 `/opsx:archive`。

### 何時跳過 opsx

- 新功能、架構變更、破壞性變更：走 opsx。
- 不改契約的 bug fix、補測試、lint 調整、非破壞性升級、typo、文件、小型設定值調整：跳過 opsx。

### 升級為 opsx 的門檻

只有以下五項全部滿足，才把口頭腦暴升級成 opsx：

1. 範圍已鎖定。
2. 主要設計分支已收斂。
3. 跨系統依賴已盤點清楚。
4. 驗收條件足夠具體。
5. 對話已進入收斂階段。

### 反模式

- 把 brainstorming 輸出寫到 `docs/superpowers/specs/`
- 把 writing-plans 輸出寫到 `docs/superpowers/plans/`
- 還有阻塞性 TBD 時就開 change
- 對低風險修復也開 change
<!-- END OPENSPEC SUPERPOWERS BRIDGE -->
