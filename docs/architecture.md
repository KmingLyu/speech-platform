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

Python Worker 是唯一需要 NVIDIA GPU 的服務。它依序執行：

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
- faster-whisper：以 CUDA/float16 執行辨識。
- Exporter：寫入結構化 JSON、TXT、SRT。

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
| `model` | 否 | 預設 `large-v3-turbo` |

成功後回傳 `202`，不等待辨識完成。

### 查詢與下載

```http
GET /v1/transcriptions/{id}
```

預設回傳 JSON 狀態。完成後內容包含純文字與可用格式。

```http
GET /v1/transcriptions/{id}?format=srt
```

直接下載 SRT。尚未完成時回傳 `409 Conflict`；工作不存在時回傳 `404`。

## 簡繁輸出轉換

`language=zh-tw` 會先以 faster-whisper 支援的 `zh` 執行辨識，再在產出檔案前使用 OpenCC 的 `s2twp.json` 轉為繁體台灣用語；`language=zh-cn` 同樣以 `zh` 辨識，再使用 `tw2sp.json` 轉為簡體中國大陸用語。單純 `zh` 或未指定時，辨識文字維持模型原始輸出。這不是翻譯，也不改變時間軸；結果 JSON 的 `metadata.output_script` 會記錄實際輸出模式。

## 現階段的限制

- Worker 失敗會將 Job 標為 `failed`；自動重試與 stale-job recovery 是下一個可靠性工作。
- `progress` 是階段式進度，ASR 執行中尚未逐 segment 回報。
- 不包含 API 認證、速率限制、TLS、反向代理與備份。
- YouTube 使用必須由部署者與呼叫者自行確認授權與平台條款。

## 未來擴充

先維持外部 API 與 Job 結果格式，並在 Worker 插入新階段：

```text
ASR → diarization → speaker alignment → translation → export
```

當 API 與 Worker 需要跨主機部署時，將 shared storage 抽換為 MinIO/S3/NAS；當不同工作類型或規模需要隔離時，再加入 Redis 或拆分 Worker。
