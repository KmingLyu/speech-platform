# Speech Platform

可自行部署的非同步 Batch ASR 服務。Client 上傳音訊／影片檔，或提交 YouTube URL；API 立即建立工作，GPU Worker 在背景下載、轉檔、使用 faster-whisper 辨識，最後產生 JSON、TXT 與 SRT。

## MVP 範圍

- `POST /v1/transcriptions`：上傳檔案或提交 YouTube URL，建立辨識工作。
- `GET /v1/transcriptions/{id}`：查詢狀態與結果。
- `GET /v1/transcriptions`：以 cursor 分頁列出工作，可用 `status` 篩選。
- `GET /v1/transcriptions/{id}?format=json|txt|srt`：下載完成產物。
- `POST /v1/transcriptions/{id}/retry`：以相同 Job ID 與設定重跑可重試的失敗工作。
- `POST /v1/transcriptions/{id}/cancel`：取消尚未完成的工作；`queued` 立即取消，`processing` 非同步取消。
- `DELETE /v1/transcriptions/{id}`：刪除 completed、failed 或 canceled 工作及其所有檔案。
- PostgreSQL 同時保存工作資料與作為簡易佇列。
- 一個 GPU Worker；可日後以 PostgreSQL row lock 擴充為多個 Worker。

目前不包含 UI、Redis、MinIO、即時辨識、speaker diarization 或翻譯。服務只應在 localhost 或私有網路使用；MVP 沒有認證、TLS 或公開網路存取控制。

## 架構

```text
Client
  │ HTTP
  ▼
FastAPI API ─────────── PostgreSQL
  │                         ▲
  │ shared /data             │
  ▼                         │
來源與結果檔案 ◀──── Python Worker ─── NVIDIA GPU
                           │
                     yt-dlp / FFmpeg / faster-whisper
```

三個長期運行的 Container：

| Service | Base image | 用途 | GPU |
| --- | --- | --- | --- |
| `api-server` | `python:3.12-slim` | HTTP API、檔案接收、結果查詢 | 否 |
| `worker` | `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04` | 媒體處理與 ASR | 是 |
| `postgres` | `postgres:17` | Job 資料、狀態與佇列 | 否 |

完整設計請見 [docs/architecture.md](docs/architecture.md)，部署步驟請見 [docs/deployment.md](docs/deployment.md)。

## 快速開始

伺服器需要 Docker Engine、Docker Compose Plugin、NVIDIA Driver 與 NVIDIA Container Toolkit。

```bash
cp .env.example .env
# 編輯 .env，至少設定 POSTGRES_PASSWORD
docker compose up -d --build
docker compose logs -f worker
```

首次執行時 Worker 會下載指定的 Whisper 模型到 `./models`；之後重啟會重用快取。

`INFERENCE_DEVICE=auto`（預設）會讓 faster-whisper 與 pyannote 分別優先使用 GPU；不可用的 backend 會降級為 CPU，並在 Worker log 記錄原因。可用 `cuda` 嚴格要求 GPU，或用 `cpu` 明確強制 CPU。

確認 GPU 容器可用：

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 nvidia-smi
```

## API 範例

```bash
curl -X POST http://localhost:8080/v1/transcriptions \
  -F file=@meeting.mp3 \
  -F language=zh-tw \
  -F model=large-v3-turbo \
  -F formats=json -F formats=srt \
  -F hotwords=PV-1 -F hotwords=軟體

curl http://localhost:8080/v1/transcriptions/tr_xxx
curl 'http://localhost:8080/v1/transcriptions?status=queued&limit=20'
curl -OJ 'http://localhost:8080/v1/transcriptions/tr_xxx?format=srt'
curl -X POST http://localhost:8080/v1/transcriptions/tr_xxx/retry
curl -X POST http://localhost:8080/v1/transcriptions/tr_xxx/cancel
curl -X DELETE http://localhost:8080/v1/transcriptions/tr_xxx
```

失敗的工作會記錄 `error.code`、已淨化的 `error.message` 與 `error.retryable`。Retryable failure 會在 `MAX_ATTEMPTS`（預設 3）的預算內自動重試；預算用完後可用上面的 retry 端點以相同 Job ID 再跑一次。Permanent failure 不會自動重試，retry 會回傳 `409 job_not_retryable`，必須改用新的 Source 或設定重新建立工作。

取消 `queued` 工作會直接變成 `canceled`，不會消耗任何 Worker Attempt；取消 `processing` 工作會回傳 `202` 並記錄 `cancel_requested`，Worker 會在下一個安全檢查點停止並確認 `canceled`，不留下可用的部分 Transcript artifact。重複呼叫 cancel 在仍為 `cancel_requested` 時是 idempotent 的；`completed`、`failed`、`canceled` 等終態工作呼叫 cancel 會回傳 `409 job_not_cancelable`。

`formats` 可重複指定 `json`、`txt`、`srt`；省略時預設產出全部三種 artifact。部署可用 `SUPPORTED_MODELS`（逗號分隔）擴充 model allowlist，`large-v3-turbo` 一律是預設模型。

`hotwords` 可重複指定，用來提高辨識器辨識出特定詞（例如 `PV-1`）的機率；每個 hotword trim 後不可為空、最多 50 字，整份清單最多 100 筆，違反時回傳 `422 invalid_hotwords` 且不會建立工作。Hotword 會依 `language` 決定的輸出字體先做繁簡轉換，再存進工作設定並於 `configuration.hotwords` 回傳；Retry 沿用相同的 hotwords。

部署操作參數的預設值為：上傳上限 2 GB（`MAX_UPLOAD_SIZE_MB=2048`）、自動 retry 最多 3 次（`MAX_ATTEMPTS=3`）、Worker heartbeat 每 5 秒（`HEARTBEAT_INTERVAL_SECONDS=5`），以及 30 秒 stale timeout（`STALE_TIMEOUT_SECONDS=30`）。檔案與結果不會自動過期；請透過 DELETE 明確刪除 terminal job。

中文地區輸出由 `language` 決定：`zh-tw` 會輸出繁體台灣用語、`zh-cn` 會輸出簡體中國大陸用語；單純使用 `zh` 或未指定時，保留模型原始輸出。轉換會套用到 JSON、TXT、SRT 和 API 回傳的文字。

## Integration tests

以下單一指令會建立隔離的 PostgreSQL 與暫存 storage、執行 API／Worker
typecheck，再跑完整 integration harness：

```bash
./scripts/test-integration
```

Harness 的 runtime network 是 internal-only，不會連到網際網路，也不會掛載 production
storage 或要求 GPU。Source acquisition、media processing 與 Transcription 使用 deterministic
fakes；測試結束後會移除測試專用 container、network 與 volume。
