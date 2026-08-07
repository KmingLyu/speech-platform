# Use ASR-segment-first diarized display segmentation

**Status: accepted**

Diarization 的 Display segment 以 ASR segment 為不可跨越的優先觀看單位：未受限制時直接保留其文字與原始時間範圍；只有 speaker 邊界或單行容量要求時，才在其內重切，並讓子 cue 使用首尾 word 時間。這取代 ADR 0023 的句末優先切分與 ADR 0024 的一律 word-timestamp timing，因為 recognizer 產生的 ASR segments 更貼近預期的觀看節奏，同時仍保留 word-level speaker attribution、單一 speaker cue 與單行字幕的約束。

**Considered Options**

- 將所有 attributed words 全域重新分組：可得到更規律的句子切點，但會忽略 ASR 對語音節奏的判斷。
- 把每個 ASR segment 不加例外地當作 cue：保留辨識器節奏，但會混合 speaker 或產生過長字幕。
- 以 ASR segment 為外框，只在必要時於其內重切：保留觀看節奏，同時滿足 diarization 與 display 的硬限制；採用。
