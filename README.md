# Speech Platform

可自行部署的非同步 Batch ASR 服務。Client 上傳音訊／影片檔，或提交 YouTube URL；API 立即建立工作，GPU Worker 在背景下載、轉檔、使用 faster-whisper 辨識，最後產生 JSON、TXT 與 SRT。

## MVP 範圍

- `POST /v1/transcriptions`：上傳檔案或提交 YouTube URL，建立辨識工作。
- `GET /v1/transcriptions/{id}`：查詢狀態與結果。
- `GET /v1/transcriptions/{id}?format=json|txt|srt`：下載完成產物。
- PostgreSQL 同時保存工作資料與作為簡易佇列。
- 一個 GPU Worker；可日後以 PostgreSQL row lock 擴充為多個 Worker。

目前不包含 UI、Redis、MinIO、即時辨識、speaker diarization 或翻譯。

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

確認 GPU 容器可用：

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 nvidia-smi
```

## API 範例

```bash
curl -X POST http://localhost:8080/v1/transcriptions \
  -F file=@meeting.mp3 \
  -F language=zh-tw \
  -F model=large-v3-turbo

curl http://localhost:8080/v1/transcriptions/tr_xxx
curl -OJ 'http://localhost:8080/v1/transcriptions/tr_xxx?format=srt'
```

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
