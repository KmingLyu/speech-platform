# 架構與責任邊界

## 目標

此 MVP 提供長時間 Batch ASR，而不讓 HTTP 請求等待媒體下載與 GPU 推論完成。每個請求先建立一筆 Job，Client 以 Job ID 輪詢結果。

## 元件

### API Server

FastAPI 服務，唯一對外公開的服務。它負責：

- 驗證 `file` 與 `youtube_url` 必須二選一。
- 將上傳檔串流寫入 `/data/jobs/{job_id}/source/`，不將整個檔案載入記憶體。
- 在 PostgreSQL 建立 `queued` Job。
- 回傳 `202 Accepted` 與 Job ID。
- 查詢 Job 的狀態與完成結果。
- 以 `?format=json|txt|srt` 回傳結果檔案。

它不執行 yt-dlp、FFmpeg 或模型推論。

### Worker

Python Worker 是唯一執行模型推論、並優先使用 NVIDIA GPU 的服務。預設會在 GPU 不可用時降級為 CPU 並留下 warning。它依序執行：

```text
queued
→ acquiring_source
→ probing
→ transcoding
→ transcribing
→ exporting
→ completed
```

- Upload：使用 API 已保存的來源檔案。
- YouTube：使用 yt-dlp 下載最佳音訊。
- `ffprobe`：取得媒體長度。
- FFmpeg：轉為 16 kHz、mono FLAC。
- faster-whisper：GPU 使用 CUDA/float16；CPU fallback 使用 int8。
- pyannote Community-1：diarization 優先移到 CUDA，無法使用時留在 CPU。
- Exporter：寫入結構化 JSON、TXT、SRT。

`INFERENCE_DEVICE=auto` 會分別探測 CTranslate2 與 PyTorch 的 CUDA 能力，因為兩個 runtime 可能得到不同結果。`cuda` 模式要求兩者都能使用 CUDA，並在不符合時 fail fast；`cpu` 模式則明確讓兩者使用 CPU。

第一版一次只處理一筆工作。要提高並行數時，應先確認 GPU 記憶體足夠；可啟動更多 Worker，但每個 Worker 都會載入一份模型。

### PostgreSQL

一張 `transcription_jobs` 表同時保存狀態與作為工作佇列。Worker 以：

```sql
SELECT ... FOR UPDATE SKIP LOCKED
```

取得工作，因此多個 Worker 不會領到同一筆 Job。

### Shared storage

Docker host 上的 `./data` 同時掛載到 API 和 Worker 的 `/data`。

```text
/data/jobs/{job_id}/
├── source/   # upload 或 yt-dlp 來源
├── work/     # 轉檔的暫存 FLAC
└── result/   # result.json、transcript.txt、transcript.srt
```

`./models` 掛載到 Worker 的 `/models`，讓模型首次下載後能跨 Container 重用。

## API 合約

### 建立工作

```http
POST /v1/transcriptions
Content-Type: multipart/form-data
```

欄位：

| 欄位 | 必填 | 說明 |
| --- | --- | --- |
| `file` | 二選一 | 音訊或影片檔案 |
| `youtube_url` | 二選一 | HTTP(S) YouTube URL |
| `language` | 否 | 例如 `zh`、`zh-tw`、`zh-cn`、`en`；不填則自動偵測 |
| `model` | 否 | 預設 `large-v3-turbo`；必須在部署設定的 allowlist 中 |
| `formats` | 否 | 可重複指定 `json`、`txt`、`srt`；省略時三者全選 |
| `hotwords` | 否 | 可重複指定的 Hotword；每個 trim 後不可為空且最多 50 字，整份清單最多 100 筆 |

成功後回傳 `202`，不等待辨識完成。

### 查詢與下載

```http
GET /v1/transcriptions?status=queued&limit=20&cursor=<opaque-cursor>
```

History 以 `created_at` 加 Job ID 穩定排序，預設每頁 20 筆、最多 100 筆；summary
不包含完整 Transcript。可用 `status` 篩選 public lifecycle status，`next_cursor`
存在時再帶回下一頁。

```http
GET /v1/transcriptions/{id}
```

預設回傳 JSON 狀態。完成後內容包含純文字與可用格式。

Job 會保存建立時的 `Source`、`language`、`model`、`formats` 與 `hotwords`；Retry 使用相同設定，不能修改既有 Job 的 Transcription configuration。

`hotwords` 會先依 `output_script` 轉換成與輸出文字相同的字體（`zh-tw` 轉繁體、`zh-cn` 轉簡體），再存進 Job 並在 `configuration.hotwords` 回傳；Worker 每次 Attempt 都把轉換後的清單以空白串接後交給辨識器當作提示。不合法的 `hotwords` 會回傳 `422 invalid_hotwords`，且不會建立 Job。`POST /v1/diarizations` 接受相同的 `hotwords` 欄位，驗證、轉換與 Retry 行為完全一致。

回應中的 `attempts.count` 是這個 Job 累計的 Attempt 次數，`attempts.automatic_count` 是目前自動重試預算已使用的次數；`error.retryable` 表示最後一次失敗是否可能靠再一次 Attempt 恢復。

### Retry

```http
POST /v1/transcriptions/{id}/retry
```

只有 `failed` 且 `error.retryable` 為 `true` 的 Job 可以人工 Retry。成功時回傳 `202` 與同一個 Job ID 的 `queued` 狀態；`queued`、`processing`、`cancel_requested`、`canceled`、`completed` 以及 Permanent failure 的 Job 都回傳 `409 job_not_retryable`；Job 不存在時回傳 `404 job_not_found`。

### Cancellation

```http
POST /v1/transcriptions/{id}/cancel
```

`queued` 的 Job 沒有 Worker 在使用它的資源，取消請求直接把它變成終態 `canceled`，回傳 `200`，且不消耗任何 Worker Attempt。`processing` 的 Job 無法被同步中止 FFmpeg 或 GPU 工作，取消請求改為記錄 `cancel_requested` 並回傳 `202`；Worker 會在 acquiring_source、probing/transcoding、transcribing、exporting 之間的下一個安全檢查點觀察到這個狀態，捨棄尚未完成的暫存音訊與 result 目錄，然後把 Job 轉為 `canceled`，不留下可用的部分 Transcript artifact。

在 Job 仍是 `queued`、`processing` 或 `cancel_requested` 時重複呼叫 cancel 是 idempotent 的，只會回傳目前狀態而不會產生額外效果。`completed`、`failed`、`canceled` 都是終態，對它們呼叫 cancel 一律回傳 `409 job_not_cancelable`；Job 不存在時回傳 `404 job_not_found`。

```http
GET /v1/transcriptions/{id}?format=srt
```

直接下載 SRT。尚未完成時回傳 `409 Conflict`；工作不存在時回傳 `404`。

```http
DELETE /v1/transcriptions/{id}
```

只有 `completed`、`failed` 與 `canceled` 等 terminal job 可以刪除；API 會移除
metadata、Source、work 與所有 Transcript artifact，成功回傳 `204`。`queued`、
`processing` 與 `cancel_requested` 必須先完成 cancellation，否則回傳
`409 job_not_terminal`。MVP 只提供 explicit deletion，不會自動清理 retention。

## 失敗分類與重試

Worker 把每次失敗分類為 Retryable failure 或 Permanent failure，並以穩定的 `error.code` 與已淨化的訊息記錄；原始工具輸出只留在 Worker log。

| `error.code` | 分類 | 典型原因 |
| --- | --- | --- |
| `source_download_failed` | Retryable | 下載逾時、暫時性網路或服務錯誤 |
| `source_unavailable` | Permanent | 來源檔案遺失、影片已移除、私人或需確認年齡 |
| `invalid_source_configuration` | Permanent | Job 的來源設定不完整 |
| `media_unreadable` | Permanent | 媒體無法 probe 或解碼 |
| `media_processing_failed` | Retryable | 轉檔失敗，可能是磁碟、記憶體或工具環境問題 |
| `processing_failed` | Retryable | 未預期的環境或程式錯誤 |

只有明確指出來源已不存在、私人或不支援的下載錯誤會判為 Permanent；其餘下載錯誤視為傳輸問題並保持 Retryable。

- Retryable failure 只在自動重試預算（`MAX_ATTEMPTS`，預設 3）還有餘額時自動回到 `queued`，用完後轉為 `failed`。
- Permanent failure 一律直接 `failed`，不自動重試，也不能人工 Retry。
- 人工 Retry 會把自動重試預算歸零，讓同一個 Job ID 重新排隊；`attempts.count` 持續累加，因此自動重試不會形成無限迴圈。
- 自動重試期間會保留上一次的 `error`，方便判斷重試原因；成功完成後才清除。

## 簡繁輸出轉換

`language=zh-tw` 會先以 faster-whisper 支援的 `zh` 執行辨識，再在產出檔案前使用 OpenCC 的 `s2twp.json` 轉為繁體台灣用語；`language=zh-cn` 同樣以 `zh` 辨識，再使用 `tw2sp.json` 轉為簡體中國大陸用語。單純 `zh` 或未指定時，辨識文字維持模型原始輸出。這不是翻譯，也不改變時間軸；結果 JSON 的 `metadata.output_script` 會記錄實際輸出模式。

## 現階段的限制

- Retryable failure 使用 bounded 自動重試與人工 Retry；Worker 以 heartbeat lease 支援 stale-job recovery，並沿用相同 retry budget。
- `progress` 是階段式進度，ASR 執行中尚未逐 segment 回報。
- 不包含 API 認證、速率限制、TLS、反向代理與備份。
- YouTube 使用必須由部署者與呼叫者自行確認授權與平台條款。

## 未來擴充

先維持外部 API 與 Job 結果格式，並在 Worker 插入新階段：

```text
ASR → diarization → speaker alignment → translation → export
```

當 API 與 Worker 需要跨主機部署時，將 shared storage 抽換為 MinIO/S3/NAS；當不同工作類型或規模需要隔離時，再加入 Redis 或拆分 Worker。
