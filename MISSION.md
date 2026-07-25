# Mission: 理解 Speech Platform 的非同步處理架構

## Why
建立對這個專案整體運作方式的心智模型，能判斷 Worker 如何取得工作、如何安全地並行，以及擴充容量時會遇到什麼限制。

## Success looks like
- 能用自己的話說明一個 transcription job 從建立到完成的路徑。
- 能判斷增加 Worker 是否安全，以及需要檢查哪些資源與一致性問題。

## Constraints
- 先以大觀念學習，不深入程式碼細節。

## Out of scope
- 本課不討論具體部署指令、程式碼實作或 GPU 效能調校細節。
