# Keep the current scope as standalone transcription jobs

**Status: accepted**

目前每次提交只代表一次獨立的 Transcription；diarization、translation、summary 與可重用的 Transcription 關聯不納入現在的產品範圍。這保留目前「提交來源、非同步辨識、下載結果」的簡單流程，避免在需求尚未驗證前引入泛用 pipeline 或可重用任務模型；未來若加入後續任務，再重新決定 Transcription 的持久化與重用邊界。

**Considered Options**

- 現在就建立可重用 Transcription 與派生任務模型：彈性較高，但會提前承擔尚未確認的領域與 API 複雜度。
- 每次提交都視為獨立 transcription job：符合目前實際需求，因此採用。
