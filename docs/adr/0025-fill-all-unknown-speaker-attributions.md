# Fill all UNKNOWN speaker attributions deterministically

**Status: accepted**

Diarization 對外結果不得保留 `UNKNOWN`。保留現有 word-level overlap attribution；只有原本無法 attribution 的 word 才使用 inferred speaker attribution：優先選時間上最近的 speaker turn，完全平手時依前一個已 attribution 的 speaker、再依後一個已 attribution 的 speaker 決勝；若整段沒有可參考的已 attribution speaker，則使用最近 turn，最後以穩定 speaker 排序決勝。補上的 label 與直接 attribution 的 label 使用相同 public schema，僅在 `attribution_statistics.inferred_word_count` 記錄推定數量。

這取代 ADR 0018 中「保留 `speaker: null` 以保存不確定性」的 attribution 行為，因為產品要求所有輸出都能分配到 speaker，且不希望為此增加資料庫欄位或逐 segment 的 public schema。

**Considered Options**

- 保留 `UNKNOWN`：最誠實地表達不確定性，但不符合所有輸出必須有 speaker 的需求。
- 只用最近 turn 並在平手時保留 `UNKNOWN`：修改較小，但仍無法保證清除所有 `UNKNOWN`。
- 以 deterministic tie-break 完成所有分配：會引入推定 label，但結果可預期、可測試，並透過 metadata 讓使用者知道推定數量；採用。
