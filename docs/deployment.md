# Server 部署

## 1. Server 前置條件

正式環境建議使用 Linux、NVIDIA GPU、相容的 NVIDIA Driver、Docker Engine、Docker Compose Plugin，以及 NVIDIA Container Toolkit。Worker 容器能啟動、但任一模型 backend 無法使用 GPU 時，預設的 `INFERENCE_DEVICE=auto` 會降級為 CPU 並在 Worker log 記錄原因，但處理速度會明顯降低。

先驗證 Docker 可以看見 GPU：

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 nvidia-smi
```

若預期使用 GPU，這個步驟失敗時應先修正 NVIDIA Driver 或 NVIDIA Container Toolkit 安裝。要刻意使用 CPU 時，請設定 `INFERENCE_DEVICE=cpu`。

> CUDA image 版本必須與 host NVIDIA Driver 相容。部署前請在實際 GPU Server 上做一次短音檔測試後，再固定 image 與 Python 套件版本。

Worker 在 build 時會安裝 yt-dlp nightly、官方 `yt-dlp-ejs` 外掛與 Deno，以因應 YouTube 經常調整的下載機制。若某次 YouTube 下載失敗，優先重新建置最新版 Worker image：

```bash
docker compose build --no-cache worker
docker compose up -d worker
```

## 2. 啟動

```bash
git clone <your-repository-url> speech-platform
cd speech-platform
cp .env.example .env
```

編輯 `.env`，至少替換：

```dotenv
POSTGRES_PASSWORD=<long-random-password>
DATABASE_URL=postgresql://speech_asr:<same-password>@postgres:5432/speech_asr
```

建議明確確認下列 MVP 操作設定（也是 `.env.example` 的預設值）：

| 設定 | 預設 | 用途 |
| --- | ---: | --- |
| `SUPPORTED_MODELS` | `large-v3-turbo` | API model allowlist；預設模型固定為 `large-v3-turbo` |
| `INFERENCE_DEVICE` | `auto` | `auto` 優先 GPU 並允許 CPU fallback；`cuda` 嚴格要求 GPU；`cpu` 強制使用 CPU |
| `ALIGNMENT_STRATEGY` | `forced_alignment` | `forced_alignment` 優先 forced alignment 並在不可用時回退至 Whisper word timestamps；`whisper_word_timestamps` 直接使用 Whisper timestamps |
| `MAX_UPLOAD_SIZE_MB` | `2048` | streaming upload safety guard |
| `MAX_ATTEMPTS` | `3` | retryable failure 的 bounded automatic retry budget |
| `HEARTBEAT_INTERVAL_SECONDS` | `5` | Worker heartbeat 頻率 |
| `STALE_TIMEOUT_SECONDS` | `30` | 判定 Worker loss 的 processing heartbeat timeout |
| `DIARIZATION_MODEL` | `pyannote/speaker-diarization-community-1` | pyannote Community-1 repository |
| `DIARIZATION_MODEL_REVISION` | 必填 | immutable Hugging Face revision；不可使用 latest |

Language preference 由 API 驗證；未指定時自動偵測，`zh-tw` 與 `zh-cn` 分別套用繁體台灣及簡體中國大陸輸出。MVP 不啟用自動 retention：Source、work、artifact 與 metadata 會保留到使用者以 `DELETE /v1/transcriptions/{id}` 刪除 terminal job。

首次部署或程式更新後：

```bash
docker compose up -d --build
```

API Server 啟動時會依序執行 `apps/api-server/migrations` 內尚未套用的 migration，
並在 `schema_migrations` 記錄版本。既有、尚未有 migration 記錄的 database 會先
baseline 原始 schema，再套用後續 migration。需要手動先執行時可使用：

```bash
docker compose run --rm api-server python -m src.migrations
```

單純重新啟動既有 image：

```bash
docker compose up -d
```

檢查：

```bash
docker compose ps
docker compose logs -f api-server
docker compose logs -f worker
curl http://localhost:8080/healthz
```

Worker 啟動時會分別記錄 faster-whisper 與 pyannote 的實際 device。任何 CPU 選擇都會產生包含 backend 與原因的 warning；例如：

```text
WARNING inference backend is not using GPU backend=pyannote requested=auto device=cpu compute_type=default reason=torch.cuda.is_available() is false
```

Smoke check（不需要 GPU 或外部網路）請執行：

```bash
./scripts/test-integration
```

此流程使用 internal-only network、隔離 PostgreSQL、temporary storage 與 deterministic fake Worker，會驗證 submit、list、poll、complete、artifact download、retry、cancellation 與 deletion。既有資料庫升級也包含在 migration tests 中；若要做真實 GPU 驗證，請完成下節的 manual smoke。

## 3. Manual GPU smoke

Before accepting diarization jobs, download and validate the configured pinned
revision. Keep the previous revision directory beside the new one for rollback:

```bash
docker compose run --rm -e PYTHONPATH=/app worker python3 scripts/prepare-diarization-model.py
docker compose restart worker
```

For a real-model smoke test, use a short authorized local recording. This is
separate from CI's deterministic fake-worker suite:

```bash
docker compose run --rm \
  -e PYTHONPATH=/app \
  -e AUTHORIZED_AUDIO_FIXTURE=/data/fixtures/short-authorized.wav \
  worker python3 scripts/smoke-diarization-model.py
```

在實際 GPU host 上先確認 `nvidia-smi`，再提交一段短、已獲授權的本地 audio/video fixture：

```bash
curl -fsS http://localhost:8080/healthz
job=$(curl -fsS -X POST http://localhost:8080/v1/transcriptions \
  -F file=@fixtures/short.wav -F formats=json -F formats=txt)
id=$(printf '%s' "$job" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
until curl -fsS "http://localhost:8080/v1/transcriptions/$id" | \
  python3 -c 'import json,sys; raise SystemExit(0 if json.load(sys.stdin)["status"] in {"completed","failed","canceled"} else 1)'; do
  sleep 2
done
curl -fso /tmp/transcript.json "http://localhost:8080/v1/transcriptions/$id?format=json"
```

確認 completed job 的 JSON/TXT 內容、segment 時間軸與語言/文字系統符合預期；此檢查只驗證功能可用性，不以 WER 或 CER 作為 MVP gate。

## 4. 資料持久性

以下資料不在 Container writable layer，而是在 host 保留：

| Host 路徑／Volume | 內容 | 備份建議 |
| --- | --- | --- |
| `postgres-data` Docker volume | Job metadata、狀態、結果文字 | 定期 `pg_dump` |
| `./data` | 原始檔、暫存檔、JSON/TXT/SRT | 依保存策略備份結果 |
| `./models` | Whisper 模型快取 | 可不備份，必要時可重新下載 |

不要執行 `docker compose down -v`，除非你確定要刪除 PostgreSQL 的所有資料。

## 5. 對外公開前

目前 Compose 直接將 API 綁定在 host 8080 port。對外服務前建議：

- 放在 Nginx、Caddy 或 Traefik 後面，並提供 TLS。
- 只允許可信 IP，或加入 API key 驗證。
- 限制 request body 大小與上傳速率。
- 設定定期清理 `/data/jobs` 過期來源檔與結果。
- 建立 PostgreSQL 備份與還原演練。

這些不是 MVP 啟動的前置條件，但未驗證身分的公開上傳 API 不應直接暴露在網際網路。
