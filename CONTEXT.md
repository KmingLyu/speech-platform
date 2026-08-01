# Speech Platform

這個 context 描述從影音來源產生語音辨識文字，並以該文字作為後續語音處理任務輸入的領域語言。

## Participants

**User**:
使用這個服務提交來源、取得 transcription，並視需要執行後續語音處理任務的人。目前產品的主要使用者是服務擁有者本人。
_Avoid_: Client（只描述技術呼叫端，不代表領域中的人）

## Inputs and outputs

**Transcription job**:
承載一次 Transcription 活動的處理工作，恰好針對一個 Source；從建立開始直到產出完整 Transcript 或失敗，具有可查詢的生命週期。Retry 不會建立新的 job。
_Avoid_: Task（未來可能代表 transcription 之後的其他處理）

**Cancellation**:
要求一個尚未完成的 Transcription job 停止處理；它不會自動刪除 job 記錄或已產生的檔案。
_Avoid_: Delete（刪除是不同的資料生命週期動作）

**Deletion**:
移除 Transcription job 的記錄及其來源、暫存與結果檔案；這是不可逆的資料生命週期動作。
_Avoid_: Cleanup（過於籠統，無法表達使用者主動刪除）

## Transcription job lifecycle

**Queued**:
Transcription job 已被接受，等待處理資源；在 Worker 開始處理前可以直接被取消。

**Processing**:
Transcription job 正在取得來源、處理媒體、執行辨識或產生輸出。

**Completed**:
Transcription job 已產生所有要求的 Transcript artifact，且每一個都可供使用者取得。

**Failed**:
Transcription job 因不可恢復的錯誤，或超過允許的 retry 次數而終止。

**Cancel requested**:
使用者要求停止正在處理中的 Transcription job，但系統尚未確認處理已安全停止。

**Canceled**:
Transcription job 已停止，且不會再繼續處理；它仍可被使用者刪除。

**Retry**:
讓已失敗的 Transcription job 以相同 job identity 再次進入處理流程；每次 retry 都增加 attempt count，並更新目前錯誤與狀態。
_Avoid_: Resubmission（會讓人以為建立了新的 job）

**Attempt**:
同一個 Transcription job 對其 Source 執行一次 Transcription 的嘗試；一次 retry 會建立新的 Attempt，但不會建立新的 job。只有成功的 Attempt 會產生可用 Transcript。
_Avoid_: Job（job 是長期身份，attempt 是其中一次執行）

**Retryable failure**:
不代表 Source 或使用者設定錯誤、仍可能因環境或暫時性服務問題恢復的失敗，例如短暫下載錯誤或 Worker 遺失。
_Avoid_: Temporary error（過於籠統，無法表達是否允許 retry）

**Permanent failure**:
即使重新執行相同 job 也預期不會恢復的失敗，例如來源格式無法解析或來源不存在；需要重新提交不同的 Source 或設定。
_Avoid_: Invalid job（有些永久失敗不是 job 建立時就能判斷）

**Source**:
使用者為一次 Transcription 指定的影音輸入及其來源資訊；目前只屬於單一 Transcription job，不是可獨立管理或重用的資產。
_Avoid_: Media（過於籠統，無法表達可追溯的輸入）

**Uploaded source**:
使用者直接提供給 Transcription job 的音訊或影片檔案。
_Avoid_: Upload（描述動作，不是來源本身）

**YouTube source**:
指向一部公開 YouTube 影片的來源資訊；實際媒體內容要在 Transcription job 處理時取得。
_Avoid_: YouTube media（容易把 URL 與下載後的檔案混為一談）

**Transcription**:
將一個 Source 轉換成文字與時間資訊的語音辨識處理活動。
_Avoid_: Transcript（指處理活動的產物，不是活動本身）

**Transcript**:
由 Transcription 活動產生的文字結果，包含純文字與可選的 Segment 時間資訊；一個成功的 Transcription job 產生一個完整 Transcript，未來的 Derived task 可以將它作為輸入。
_Avoid_: Transcription（不要用處理活動的名稱稱呼結果內容）

**Timestamped format**:
保留 transcription 片段起訖時間的輸出格式，例如 JSON 或 SRT；純文字 TXT 不要求時間資訊。
_Avoid_: Timed text（本專案對外使用較不一致）

**Language preference**:
使用者提交 transcription 時對語音語言與中文地區文字用法的單一偏好設定；未指定時由辨識器自動偵測。
_Avoid_: Locale（目前 API 的用途不只表示地區）

**Transcription configuration**:
一個 Transcription job 建立時確定的 Source、Language preference、model 與 Output format 選擇；同一 job 的 Retry 不會修改這些設定。
_Avoid_: Runtime option（設定屬於工作本身，不是每次 Attempt 臨時改變的選項）

**Output script**:
Transcription 文字使用的文字系統與地區用語；目前由 `Language preference` 隱含決定，`zh-tw` 對應繁體台灣用語、`zh-cn` 對應簡體中國大陸用語。
_Avoid_: Translation（文字系統轉換不改變語意，也不是翻譯）

**Segment**:
Transcription 中一段連續語音及其文字，至少包含 `start`、`end` 與 `text`；目前時間軸粒度只到 segment，不包含逐詞時間。
_Avoid_: Word timestamp（尚未納入目前範圍）

**ASR segment**:
faster-whisper 產生的原始 transcription 片段，保留辨識器給出的文字與時間，並可在內部帶有 word timestamps；它不是 diarization 對外下載 artifact 的字幕單位。
_Avoid_: Display segment（為觀看而切分的最終字幕單位）

**Display segment**:
由已完成 speaker attribution 的文字與時間資訊導出的單行字幕 cue，具有自己的 `start`、`end`、主要文字與可選 speaker；diarization 的對外 artifact 使用它，而不覆寫 ASR segment。
_Avoid_: Line break（只是同一 cue 的排版）、ASR segment（辨識器原始輸出）

**Transcript artifact**:
由 Transcription job 產生、可供下載的特定格式 Transcript，例如 JSON、TXT 或 SRT。
_Avoid_: Result（可作一般描述，但正式領域詞使用 artifact 以強調格式化產物）

**Output format**:
同一個 Transcript 的呈現方式，例如 JSON、TXT 或 SRT；選擇不同格式不會建立不同的 Transcription。
_Avoid_: Transcription type（格式不是不同的辨識類型）

**Derived task**:
以既有 Transcript 或其時間資訊為輸入的後續處理，例如 speaker diarization、translation 或 summary。目前不屬於產品範圍，未決定其是否能獨立重跑。
_Avoid_: Feature（無法表達它和 Transcription 的依賴關係）

**Diarization**:
將一個 Source 的語音切分為 speaker turns，為每段語音賦予同一個處理範圍內有效的匿名 speaker label；本專案的 diarization API 會先完成 Transcription，再執行 diarization 與 alignment。
_Avoid_: Speaker identification（本專案不辨識真實人物身份）

**Speaker turn**:
由同一位 speaker 連續說話所形成的語音時間區間；它是 diarization 的時間結果，不等同於 Whisper 的 Segment。
_Avoid_: Speaker segment（容易與 Transcription 的 Segment 混淆）

**Alignment**:
將 Transcript 的文字單位與音訊時間軸及 speaker turns 對齊的處理；內部可使用 word-level 時間資訊，但對外結果目前只公開重新合併後的 Segment。
_Avoid_: Synchronization（過於籠統，無法表達文字與 speaker 時間的對應）

**Diarized transcript**:
由 Diarization 產生的 Transcript，由 Display segment 組成，除文字與時間外還包含匿名 speaker label；speaker label 只在單一 job 內有效。
_Avoid_: Identified transcript（不代表真實身份）
