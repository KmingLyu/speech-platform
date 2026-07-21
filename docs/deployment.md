# Server 部署

## 1. Server 前置條件

目標 Server 需要 Linux、NVIDIA GPU、相容的 NVIDIA Driver、Docker Engine、Docker Compose Plugin，以及 NVIDIA Container Toolkit。

先驗證 Docker 可以看見 GPU：

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 nvidia-smi
```

這個步驟失敗時，不要先啟動本專案；請先修正 NVIDIA Driver 或 NVIDIA Container Toolkit 安裝。

> CUDA image 版本必須與 host NVIDIA Driver 相容。部署前請在實際 GPU Server 上做一次短音檔測試後，再固定 image 與 Python 套件版本。

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

首次部署或程式更新後：

```bash
docker compose up -d --build
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

## 3. 資料持久性

以下資料不在 Container writable layer，而是在 host 保留：

| Host 路徑／Volume | 內容 | 備份建議 |
| --- | --- | --- |
| `postgres-data` Docker volume | Job metadata、狀態、結果文字 | 定期 `pg_dump` |
| `./data` | 原始檔、暫存檔、JSON/TXT/SRT | 依保存策略備份結果 |
| `./models` | Whisper 模型快取 | 可不備份，必要時可重新下載 |

不要執行 `docker compose down -v`，除非你確定要刪除 PostgreSQL 的所有資料。

## 4. 對外公開前

目前 Compose 直接將 API 綁定在 host 8080 port。對外服務前建議：

- 放在 Nginx、Caddy 或 Traefik 後面，並提供 TLS。
- 只允許可信 IP，或加入 API key 驗證。
- 限制 request body 大小與上傳速率。
- 設定定期清理 `/data/jobs` 過期來源檔與結果。
- 建立 PostgreSQL 備份與還原演練。

這些不是 MVP 啟動的前置條件，但未驗證身分的公開上傳 API 不應直接暴露在網際網路。
