# VERA Nexus v0.3.0 開發與部署

VERA 收到經授權的工作後，負責安排語音聯繫、保存逐字稿、整理摘要並回收明確的決策及指示。ChatGPT 或原工作系統可依工作 ID 取回結果並接手執行。現有 FCM 專案與 Render 磁碟沿用。Gmail、Firestore 和 Firebase Storage 沒有新增。

## 資料與相容性

- 既有 Android v0.2.1 仍使用 `/app`、原有登入、FCM 註冊和語音 API。新版使用 `/app/v3`。新版在舊 Render 找不到 `/app/v3` 時會回到 `/app`。
- v0.3.0 新資料使用同一個 `VERA_PUSH_DB`。遷移在 SQLite 交易中新增 `vera_work_*` 表，不更改裝置、雲端來電與回執的資料表。新版工作關聯只包含 ID 進入 FCM 來電傳輸。工作內容需在接聽與驗證後取得。
- 原生 v0.3.0 的新本機資料使用 Android Keystore AES-GCM。既有 WebView 資料使用原本欄位讀取，供回退使用。新版可讀取 v0.2.1 的 JSON 備份，匯出時用個別密碼、隨機鹽值與 AES-GCM 保護。備份涵蓋本機來電、工作、決策、記憶及偏好，排除登入憑證。刪除本機資料時會清理新舊欄位。
- 雲端工作簡報、記憶、逐字稿、摘要及結果欄位用 `VERA_DATA_KEY` 加密。通話顯示資料記錄實際缺漏。雲端記憶出入庫以同伺服器金鑰驗證，匯入時合併新 ID。跨環境整庫還原使用 SQLite 快照與原金鑰。
- 確保新環境有 `VERA_PUSH_DB=/var/data/vera-push.sqlite3`、既有 `VERA_ACCESS_TOKEN`、OpenAI 憑證、現有 Firebase Secret File，以及獨立的 `VERA_DATA_KEY`。Render 只設定來源 Token 的 SHA-256 摘要 `VERA_WORK_TOKEN_SHA256`，原始 Token 由授權的呼叫者保存在服務端。不要使用手機登入憑證作為工作來源 Token。

## 工作來源與結果

| 動作 | 方法與路徑 |
|---|---|
| 發布工作 | `POST /api/v1/work/tasks`，欄位 `source_id`、`title`，選填 `brief`、`project`、`priority`、`due_at` |
| 查詢工作 | `GET /api/v1/work/tasks` 或 `GET /api/v1/work/tasks/<id>` |
| 更新工作 | `PATCH /api/v1/work/tasks/<id>`，帶目前 `revision`，版本競爭回 409 |
| 取消工作 | `DELETE /api/v1/work/tasks/<id>`，JSON 帶目前 `revision`，同時取消該工作待發來電 |
| 安排聯繫 | 手機工作室或 `POST /api/v1/secretary/tasks/<id>/call`，使用手機擁有人授權 |
| 取回結果 | `GET /api/v1/work/results?after=<cursor>` |
| 接續結果 | `GET /api/v1/work/inbox/<consumer>`，傳回 `acknowledged` 和最多 50 筆 `results` |
| 確認結果 | `PUT /api/v1/work/inbox/<consumer>`，傳送先前的 `after` 和本批已依序處理的 `cursors` |

工作來源使用 `Authorization: Bearer` 和獨立來源 Token。伺服器回傳 `next_cursor`。每次消費需先保存或處理本批結果，再保存新的游標。中途失敗可用原游標重讀，依工作 ID 和結果游標去重。結果只包含擁有人已選擇回傳的、逐字稿中有使用者原文支持的決策和指示。原文佐證、逐字稿、私人摘要和記憶保留在擁有人端。工作「已回傳」表示秘書已回報，後續執行由工作來源追蹤。

工作來源可使用專屬讀取者名稱在服務端保存確認位置。確認必須包含先前讀到的有序結果游標，重送最近已接受的相同批次安全。遇到 409 時重新讀取；每一筆對外執行仍以原工作 ID 與結果游標作為去重依據。這個機制允許新的授權執行階段接續讀取，也能在處理中斷後重讀。

## ChatGPT Sites 和 Work

`sites/vera-bridge/worker.mjs` 是 Sites 的私人 MCP 橋接程式。部署時將 `hosting.template.json` 的 `capabilities` 合併到該 Site 的 `.openai/hosting.json`，將 Worker 保存為 `dist/server/index.js`。須先取得真正的私人 Site ID 並確認具備工具發布能力。擁有人登入私人 Site 後可從首頁讀取自己的 `site_user_id` 並設為 Worker 私密變數 `VERA_SITE_OWNER_ID`，另設定 `VERA_WORK_TOKEN`。API 只接受官方 Sites 轉交的指定身分和服務端憑證。此橋接的目標固定是既有 Vera Nexus Render 服務。

獨立私人的 VERA 隔離站以合成資料驗證 Sites 可發布 MCP 並配置 Plugin。正式橋接的八項工具，含 `resume_work` 與 `ack_results`，有本機權限與路由測試。接通正式資料前，需驗證個人帳戶的 Plugin 連接、Work 的工具權限以及排程執行環境的身分。排程的驗收證據包括執行紀錄、讀取游標、去重及下一次零筆的觀察。以新的授權工作讀取結果並依原工作 ID 接續，是目前可採用的流程。原始 ChatGPT 對話是否能由外部服務喚醒仍未驗證。

官方資料 [ChatGPT Plugins](https://learn.chatgpt.com/docs/plugins) · [ChatGPT Work](https://learn.chatgpt.com/docs/get-started-with-work) · [ChatGPT 排程任務](https://help.openai.com/en/articles/10291617-scheduled-tasks-in-chatgpt)。

## 隔離預先驗收

1. 先執行後端和橋接測試，以獨立的暫存 SQLite 測相容性、結果回讀、備份與還原。各頁在不同寬度核對導覽、換行和主要操作。
2. 使用 `gradle :app:assembleDebug -PveraQaPort=18730` 產生模擬器 QA APK。此 APK 指向模擬器的 `127.0.0.1:18730`。以 `adb -s <模擬器 ID> reverse tcp:18730 tcp:18730` 建立虛擬裝置到工作站的連線，並以合成登入和獨立加密金鑰啟動 `python vera_qa.py --db <QA 目錄>/vera.qa.sqlite3`。一般 APK 使用現有 Render HTTPS。
3. 在可啟動的模擬器，用同一簽章依序裝入版本 10 和 11，確認舊資料留存。僅於該隔離模擬器核對舊正式 APK 的不同簽章更新結果。驗收紀錄須分別保存建置、套件簽章、模擬器和實機結果。
4. 最後集中以一台正式驗收手機確認鎖屏、背景通知、響鈴震動、接聽後主動開口與插話、掛斷後自動摘要及決策回傳。全螢幕和背景限制依 Android 設定與廠牌而異。原有 v0.2.1 需先備份並驗證轉移流程，才可更換簽章。

## 快照、回復與發布

1. 部署前在 Render 的安全儲存位置保留 SQLite 線上快照。先確認剩餘空間、部署前的版本 ID 和必要的金鑰復原方式。 `python vera_db_backup.py /var/data/vera-push.sqlite3 <受保護的快照路徑>` 會使用 SQLite Backup API，檢查完整性並報告既有表筆數。快照含正式裝置資料，請限制權限。留存資料庫及其加密金鑰時請分開保管。
2. 用隔離副本重跑資料遷移，檢查舊裝置、排程與回執數，並確認快照可還原至新路徑。發生新版本程式問題時，優先切回可用的舊部署並保留同一顆磁碟。只有錯誤已影響資料才在停止寫入後選擇回復快照，先另存現況。回復前的新增資料需另行保留。
3. 公開發布需使用經核對的長期簽章。本次 `versionCode` 為 11。v0.2.1 `26-r2` 的憑證 SHA-256 是 `090145966eb3fa965d896e9ff7dcff09d54b418349b11ba8639a2ffcce41be4e`。本次本機簽章不同，Android 無法直接覆蓋 v0.2.1。若舊簽章私鑰仍無法取得，保留現有安裝，先在隔離環境驗證匯出、還原、新簽章安裝與裝置重新註冊。新簽章私鑰及其解鎖資料需在安全儲存位置保存，以支援日後同簽章升級。
4. GitHub Actions 一般建置只存 APK 成品。正式發布入口需要已驗收簽章的密碼和私鑰 Secrets、Firebase 用戶端設定、以及操作者開啟發布。發布前可用 `VERA_UPGRADE_CERT_SHA256` 指定已完成轉移驗收的新簽章。Render 的 `VERA_RELEASE_CERT_SHA256` 要對應已核可的指紋。更新入口會檢查發布檔案的 SHA-256、完整版本／包名和簽章證明。手機系統仍負責驗證 APK 簽章。
5. 目前 `vera-mvp` 推送會觸發現有 Render 自動部署。前置驗收未完成時，本機候選提交先留在本機，部署和正式發布分開核對。上線後用舊 APK 及新 APK 各收一筆測試推播，核對版本回應與真實接聽紀錄。

## OpenAI 模型與費用

正式 v0.2.1 使用 `gpt-realtime`、`gpt-4o-mini-transcribe` 和 `gpt-4.1-mini`。v0.3.0 以 `gpt-realtime-2.1`、`gpt-transcribe` 和 `gpt-6-luna` 作為預設。舊路徑可透過 `OPENAI_REALTIME_MODEL`、`OPENAI_TRANSCRIBE_MODEL`、`OPENAI_SUMMARY_MODEL` 在驗收後切換。新版以相應的 `VERA_V3_REALTIME_MODEL`、`VERA_V3_TRANSCRIBE_MODEL`、`VERA_V3_SUMMARY_MODEL` 覆寫。

OpenAI 公告 `gpt-realtime` 於 2027 年 1 月 20 日停用，`gpt-4o-mini-transcribe` 於 2027 年 2 月 26 日停用，`gpt-4.1-mini-2025-04-14` 快照於 2027 年 1 月 14 日停用。先完成話機和摘要驗收再切換正式用量。當前新版在通話限時未設定時使用 20 分鐘預設，最多接受 80 筆雲端通話整理／24 小時。顯示本機可取得的用量和即時音訊費用估算，帳單仍以 OpenAI 為準。現有 Render、1 GB 磁碟和 FCM 維持原方案。

官方資料 [OpenAI 模型停用](https://developers.openai.com/api/docs/deprecations) · [OpenAI API 價格](https://developers.openai.com/api/docs/pricing) · [Android 簽章](https://developer.android.com/studio/publish/app-signing) · [Render 持久化磁碟](https://render.com/docs/disks)。
