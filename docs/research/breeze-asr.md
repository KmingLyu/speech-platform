# Breeze-ASR 研究與整合評估

研究日期：2026-11-06。本文以官方模型卡、官方程式與論文為依據；沒有在本專案硬體上執行模型或量測效能。整合建議屬於待驗證方案。

實作更新：系統現已提供 `model=breeze-asr-25`，採固定官方 revision、自行轉換 CT2 與現有 word-timestamp pipeline。模型切換會卸載舊 ASR 模型。操作方式見 [部署文件](../deployment.md#breeze-asr-25)；下方整合建議保留為研究時的評估，真實模型效能與時間戳精準度仍待目標硬體驗證。

## 先分清楚 25 與 26

| 項目 | Breeze-ASR-25 | Breeze-ASR-26／BreezeASR-Taigi |
| --- | --- | --- |
| 定位 | 台灣華語、中英混用 | 台語音訊轉華語漢字 |
| 基礎架構 | Whisper large-v2 微調 | Whisper large-v2 微調 |
| 主要應用 | 華語會議、課程、字幕 | 台語內容的華語文字呈現 |
| 權重授權 | Apache-2.0 | Apache-2.0 |
| 本系統優先順序 | 適合優先驗證 | 應作為獨立台語選項評估 |

25 的定位與授權見 [官方模型卡](https://huggingface.co/MediaTek-Research/Breeze-ASR-25)。26 明確輸出華語漢字，並非台語正字；方言、強烈地方口音、領域術語仍有限制。因此 26 不能僅憑版本號視為 25 的全面升級。[26 官方模型卡](https://huggingface.co/MediaTek-Research/Breeze-ASR-26)

## 已公開的品質證據

25 官方表格列出的 CommonVoice16-zh-TW 錯誤率為 7.97，Whisper large-v2 auto 為 9.84；CSZS-zh-en 為 13.01 對 29.49。但 Formosa-Course 為 9.94，略差於 large-v2 的 9.50，顯示並非每種音訊都改善。[25 官方模型卡](https://huggingface.co/MediaTek-Research/Breeze-ASR-25)

論文採用 MER：中文以字、英文以詞計算錯誤；不能把中英混用表格直接解讀成全中文 CER。論文也說明以中英文語言 token embedding 的平均值初始化共用 embedding，這是跨執行引擎驗證時需要檢查的語言提示行為。[25 論文，IV-C／IV-E](https://arxiv.org/html/2506.11130v1)

26 論文的 30.13% 平均 CER 來自 30 組行政院華台語公共廣播對照樣本，每段約 30 秒，參考答案是華語文字。這不是長會議、多人重疊語音或台語正字逐字稿的驗證，不能外推為本系統品質保證。[26 論文](https://arxiv.org/html/2603.19259v1)

## 推論方式與相容性

### 官方基準路徑

25 官方範例使用 PyTorch、torchaudio、Transformers 的 `WhisperProcessor`、`WhisperForConditionalGeneration` 與 `AutomaticSpeechRecognitionPipeline`。音訊轉單聲道及 16 kHz；模型移至 CUDA；`chunk_length_s=0`、`return_timestamps=True`。[官方 run.py](https://github.com/mtkresearch/Breeze-ASR-25/blob/main/run.py)

官方 README 建議長音訊使用上述 sequential pipeline，並提供 patched Whisper CLI 產生字幕。程式碼倉庫標示 MIT，與模型權重 Apache-2.0 要分開記錄。[官方 GitHub README](https://github.com/mtkresearch/Breeze-ASR-25)

25 與 26 的 config 都使用標準 `WhisperForConditionalGeneration`、80 mel bins、51865 vocab；config 所記的 Transformers 版本分別為 4.48.3、4.49.0，這是模型產出資訊，並不等於官方保證的最低依賴版本。[25 config](https://huggingface.co/MediaTek-Research/Breeze-ASR-25/blob/main/config.json)、[26 config](https://huggingface.co/MediaTek-Research/Breeze-ASR-26/blob/main/config.json)

### CTranslate2／faster-whisper 路徑

faster-whisper 官方支援將 Transformers 相容的 Whisper 微調模型轉為 CTranslate2，並從本地目錄載入；支援 GPU FP16、GPU INT8／FP16、CPU INT8。這支持「自行轉換官方 Breeze snapshot」作為整合候選方案，但不代表 Breeze 的解碼、時間戳、語言提示與官方範例已經實測等價。[faster-whisper 官方轉換文件](https://github.com/SYSTRAN/faster-whisper#model-conversion)

25 的 tokenizer.json 可在官方權重倉庫取得；轉換時需攜帶 tokenizer 與 preprocessor，避免執行時另抓其他模型 tokenizer。[25 官方檔案列表](https://huggingface.co/MediaTek-Research/Breeze-ASR-25/tree/main)

## 功能邊界

| 能力 | 證據與限制 |
| --- | --- |
| Segment timestamps | 25 官方範例有開啟。需驗證轉換後完整保留。 |
| Word timestamps | faster-whisper 提供 `word_timestamps=True`；25／26 generation config 均帶 alignment heads，但這仍不構成 Breeze 在本系統中的字詞對齊品質保證。 |
| Hotwords | faster-whisper `transcribe` 有 `hotwords`、`initial_prompt`；屬提示而非強制字典，尚未看到 Breeze 官方專屬評測。 |
| Speaker diarization | 已查閱的 Breeze 模型與官方範例沒有 speaker labels；仍需外部 diarization pipeline。 |
| 長音訊 | 25 有官方 sequential 路徑與長音訊評測；26 公開 benchmark 主要是約 30 秒音訊，長會議能力待測。 |
| Streaming | 沒有在已查官方資料找到 Breeze 原生串流介面／延遲保證；faster-whisper 生態可另做近即時政策，不能視為模型自帶能力。 |

字詞時間與提示 API 見 [faster-whisper transcribe.py](https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/transcribe.py)；alignment heads 見 [25 generation config](https://huggingface.co/MediaTek-Research/Breeze-ASR-25/blob/main/generation_config.json) 與 [26 generation config](https://huggingface.co/MediaTek-Research/Breeze-ASR-26/blob/main/generation_config.json)。

## 硬體與部署：已知與未知

25 的主要 safetensors 約 3.09 GB；26 的兩個 shards 合計約 6.17 GB。檔案大小不等於執行時 VRAM。[25 官方檔案列表](https://huggingface.co/MediaTek-Research/Breeze-ASR-25/tree/main)、[26 官方檔案列表](https://huggingface.co/MediaTek-Research/Breeze-ASR-26/tree/main)

faster-whisper 官方 large-v2 參考測試在 RTX 3070 Ti 8 GB：FP16 約 4525 MB VRAM，INT8 約 2926 MB；這是上游 large-v2 測試，**不是 Breeze 實測，也不包含本系統 pyannote 等模型同時駐留的成本**。[faster-whisper 官方 benchmark](https://github.com/SYSTRAN/faster-whisper#benchmark)

目前查閱來源未提供可直接當成 Breeze 生產規格的最低 VRAM、峰值 RAM、目標硬體 RTF、長會議 OOM 邊界。應量測模型載入／切換、轉錄與 diarization 全流程峰值，不能只以權重檔案大小規劃容量。

## 尚待驗證

- 官方 snapshot 經 CT2 轉換後，auto／zh／en 對中英混用的影響，以及與官方 Transformers 輸出差異。
- 轉換後 segment 與 word timestamps 的完整性、邊界準確度、跨語言與長靜音行為。
- 熱詞提示與既有繁簡處理是否提高專有名詞正確率，而不增加幻覺。
- 若開放 26：產品是否接受華語漢字輸出；若要求台語正字，這份 checkpoint 的輸出語義不符需求。
- 長錄音的 RTF、峰值 VRAM／RAM、模型切換與 diarization 共用 GPU 時的資源成本。

## 對這個系統的整合建議

以下是依目前 repository 原始碼提出的設計建議，尚未執行模型下載、格式轉換或 GPU 實測。

### 建議方向：Breeze-ASR-25 作為可選模型，沿用 faster-whisper

以台灣華語與中英混用為目標，先加入 25；保留 `large-v3-turbo` 預設值。26 應在有台語需求時獨立評估，其華語漢字輸出不等於台語正字逐字稿，也不能透過 OpenCC 補足這項差異。

推薦流程：

```text
建立 job，model 選擇 Breeze 的版本化識別碼
  → PostgreSQL queue
  → 現有 Worker：取得來源 → FFmpeg 16 kHz mono FLAC
  → 模型識別碼解析為已準備的本地 CT2 目錄
  → 現有 Transcriber / faster-whisper
  → 現有中文正規化
  → transcription：直接輸出 JSON / TXT / SRT
  → diarization：word alignment → pyannote → attribution → display segmentation → 輸出
```

這條路徑的依據是 faster-whisper **v1.1.1** 官方文件明確支援將 Transformers 格式的 Whisper 微調模型轉為 CTranslate2，並從本地目錄載入。這是架構可行性的依據，並非 Breeze 在本專案已通過相容性測試。[faster-whisper v1.1.1：Model conversion](https://github.com/SYSTRAN/faster-whisper/blob/v1.1.1/README.md#model-conversion)

### 現有接點與必要修改

| 位置 | 目前實作 | 建議 |
| --- | --- | --- |
| `apps/api-server/src/config.py`、`main.py` | `SUPPORTED_MODELS` 控制 allowlist；兩種 job 都接受 `model` | 加入已完成部署驗證的版本化模型識別碼，維持預設模型；不需新增 endpoint |
| `apps/worker/src/transcriber.py` | `model_name` 直接傳給 `WhisperModel` | 在載入前解析模型識別碼為本地 CT2 路徑；不可把官方 Transformers repo ID 當作 CT2 模型直接傳入 |
| `apps/worker/src/model_registry.py` | 名稱雖是 registry，目前只處理 pinned diarization 模型 | 新增明確的 ASR 模型描述與驗證；不要直接沿用 diarization 的 `config.yaml` 完整性判斷 |
| `scripts/`、`compose.yaml`、`.env.example` | 已有 diarization 準備腳本與共享 `/models` | 增加 ASR 準備與 smoke 腳本，預先下載／轉換／驗證，Worker 掛載既有 models 目錄 |
| `apps/worker/src/processor.py` | `TranscriptionEngine` 已隔離 ASR，後面沿用統一 segment shape | 保持介面與 job lifecycle；避免為單一模型新增完整 pipeline |
| `apps/worker/src/dependencies.py`、`alignment.py` | production forced aligner 是 `None`，實際回退到 Whisper word timestamps | Breeze 必須產生可用 `words` 才能延用 diarization；只驗證有文字或 SRT 不足以開放此模型到 diarization API |
| `apps/worker/src/script_converter.py` | `zh-tw` 送 ASR 時映射 `zh`，ASR 後統一 OpenCC | 維持既有行為，Hotwords 原文傳遞，不在 Breeze adapter 再做一次繁簡轉換 |

**不能只改 `SUPPORTED_MODELS` 就算整合完成。** 它只是 API 接受清單，沒有提供模型轉換、版本固定或 Worker readiness 檢查。`WHISPER_MODEL` 雖出現在 Worker settings，目前 `process_job` 是直接使用 job 的 `model`；修改該環境變數也不會改變 API 的預設模型。

模型準備建議以官方 snapshot 的完整 commit SHA 為來源，在獨立準備環境轉換；固定 converter、Transformers 與 CTranslate2 版本，保存來源 revision、轉換參數、檔案雜湊與授權。Worker runtime 不需因此增加 Transformers ASR backend。轉換概念如下（佔位路徑，尚未執行）：

```bash
ct2-transformers-converter \
  --model /models/source/Breeze-ASR-25/<upstream-commit> \
  --output_dir /models/asr/<immutable-model-id> \
  --copy_files tokenizer.json preprocessor_config.json \
  --quantization float16
```

先下載固定 snapshot，再以本地路徑轉換；檢查 tokenizer 與 preprocessor 檔案都存在，避免載入時再隱性連網取得其他版本。轉換後要驗證 alignment 設定及實際 word timestamps，不能假設 Transformers 的所有 generation 設定會在另一個 runtime 等效生效。[CTranslate2 Transformers 支援](https://opennmt.net/CTranslate2/guides/transformers.html)、[Breeze-ASR-25 generation config](https://huggingface.co/MediaTek-Research/Breeze-ASR-25/blob/main/generation_config.json)

公開 `model` 建議採版本化識別碼，例如 `breeze-asr-25-<sha8>-ct2-fp16`，映射到不可覆寫的本地目錄；同一識別碼不可在部署後重新指向不同權重。這樣 Retry 仍使用相同模型。保留舊版 artifact 直到仍可 Retry 的工作不再需要它。既有資料庫 `model VARCHAR(64)` 可容納這類識別碼，第一版通常不需要 schema migration；若之後要記錄完整推論 provenance，可考慮 artifact metadata，另行定義契約。

### 三項上線前必須確認的風險

1. **時間戳與 speaker attribution。** 現在 `Transcriber` 已設定 `word_timestamps=True`，但 production 沒有真正獨立的 forced aligner。若 Breeze 的 words 缺漏或時間漂移，現有 fallback 不能自行修好。先驗證 transcription，再用真實多人錄音測 diarization；未通過前只開放 transcription，並在建立 diarization job 前明確拒絕不具能力的模型組合。
2. **GPU 常駐記憶體。** `Transcriber._models` 是不淘汰的 dict；即使一次只跑一個 job，先跑 turbo 再跑 Breeze，兩個模型仍可能同時駐留，再疊加 pyannote。建議第一版限制一個 ASR 模型駐留，切換時使用 backend 的卸載機制並實測釋放；若不足再採每次推論子程序隔離。CPU fallback 必須保留可觀察性，也不能把它當成 VRAM 問題已解決。
3. **推論設定與 Hotwords。** 先沿用目前 `beam_size=5`、VAD 與 Hotwords 傳遞，建立公平基線，再單獨比較 VAD、language auto／`zh`、Hotwords 有無的效果。faster-whisper 提供 hints 不代表 Breeze 一定因此更準；也不能把語音混用能力等同於目前單次語言偵測模式已最佳化。[faster-whisper v1.1.1 推論原始碼](https://github.com/SYSTRAN/faster-whisper/blob/v1.1.1/faster_whisper/transcribe.py)

另一個可行選項是實作 `TransformersTranscriptionEngine`，用官方推論方式做基準。它會增加 runtime 依賴、PyTorch ASR 裝置與記憶體管理、長音訊處理及結果轉換責任；適合當 CT2 出現實質相容性問題時再採用。獨立 ASR HTTP 服務則會引入網路失敗與額外部署，對目前單一 GPU Worker 的需求收益有限。

### 建議實作順序與驗收

1. **離線比較，先不變更正式 API。** 準備官方固定版 25 與 CT2 模型，用同一批人工校對錄音對照目前 `large-v3-turbo`。涵蓋台灣華語、中英技術名詞、英文、噪音、靜音、多人插話與至少一段 30–60 分鐘長音訊；這些時長與案例是建議測試設計。
2. **完成模型準備與載入。** 加入版本化模型解析、完整性檢查、smoke test 與記憶體淘汰。比對官方 Transformers 與 CT2 的文字／時間品質，確認轉換沒有明顯退化。
3. **先開放 transcription。** 加 allowlist、部署文件與範例；驗證 JSON／TXT／SRT、Hotwords、中文正規化、取消、Retry 與既有模型回歸。取消仍依現有安全檢查點生效；不應宣稱能立即中斷長時間模型推論。
4. **通過 alignment 評估再開放 diarization。** 檢查 speaker 邊界、漏字／重字、word coverage、Display segment 時間，以及 `inferred_word_count`。所有詞都有 speaker label 不等於 attribution 正確，因 ADR 0025 會補上推定 speaker。

每批測試記錄：中文 CER、中英混用 MER（固定並公開分詞／正規化規則）、專有名詞命中與誤插入、字幕邊界偏差、RTF（推論秒數／音訊秒數）、冷啟動／暖啟動時間、GPU peak memory、長音訊重複／幻覺與失敗率。文字品質同時看原始 ASR 與既有 OpenCC 後的結果；不要把字體正規化帶來的差異全歸因於辨識模型。

現有 integration harness 使用 deterministic fakes，能驗證 API 與生命週期，**不能證明真實 Breeze 推論、CT2 轉換、GPU 容量或時間戳品質**；需要額外的實機 benchmark／smoke。公開 benchmark 亦不能直接證明 25 勝過本系統的 turbo。

### 與既有決策的關係

- 維持 ADR 0007（可選模型與穩定預設）、0015（序列 GPU jobs）、0022（可觀察的裝置 fallback）、0027／0029（Hotwords 原文與單次正規化）。
- 維持 ADR 0025／0026 的 word attribution 與 ASR-segment-first display 規則；時間戳驗證是接入前提，不能換成每個 segment 指派單一 speaker 當作捷徑。
- 若採更換預設模型、模型不支援 word timestamps 卻直接開放 diarization，或把 26 的華語漢字輸出稱為台語原文逐字稿，需要另行釐清產品契約與記錄決策。本研究沒有修改既有 ADR 或接受上述行為。

**建議下一步是先做 Breeze-ASR-25 的固定版本 CT2 benchmark，再以可選模型方式加入。** 是否改預設，應由本系統的真實錄音品質、延遲與 GPU 記憶體結果決定。
