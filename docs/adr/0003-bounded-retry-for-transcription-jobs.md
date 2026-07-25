# Use bounded retries for transcription jobs

**Status: accepted**

Transcription job 只對標記為 `Retryable failure` 的錯誤自動重試，最多重試 2–3 次；輸入無效、來源不可用、格式不支援等 `Permanent failure` 直接進入 `failed` 且不可 retry。自動重試超過上限後不得自行回到 queue，但可由使用者明確觸發一次人工 retry，避免自動錯誤循環，同時讓短暫的網路、worker 或服務故障可以自行恢復。

**Considered Options**

- 所有錯誤都自動 retry：實作簡單，但會讓永久性錯誤形成無限迴圈或浪費 GPU／下載資源。
- 完全不 retry：狀態簡單，但短暫故障必須人工重新提交，且可能需要重新上傳來源。
- 依錯誤分類並限制次數：兼顧恢復能力與可控性，因此採用。
