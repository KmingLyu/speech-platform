# Preserve attributed timestamps in diarized display segmentation

**Status: accepted**

Diarization 的 Display segment 必須保留 speaker-attributed word 的既有時間範圍；字幕切割不得為最短顯示時長、最長 cue 時長、閱讀速率或相鄰 cue 的連續性而延長、縮短或推移時間。句末標點、speaker 邊界與行長是切割語意與排版規則，其中行長僅在句末標點分割後仍過長時適用；這取代 ADR 0023 中允許以文字比例估算 Display timing 的決定。

**Considered Options**

- 以最短時長、最大時長和閱讀速率校正時間：閱讀體驗較一致，但會使字幕偏離原始音訊時間。
- 維持 attributed word 時間並只切分 cue：保留音訊同步，接受不同 cue 的時長與閱讀密度；採用。
