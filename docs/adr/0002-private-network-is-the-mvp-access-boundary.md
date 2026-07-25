# Use a private network as the MVP access boundary

**Status: accepted**

MVP 的 Speech Platform 只在使用者的本機或私有網路提供服務，將網路邊界視為主要存取控制；目前不建立帳號、API key、TLS termination 或公開租戶模型。這符合目前單一使用者的部署情境，但若未來要直接暴露到網際網路，認證、限流、配額、TLS 與資料隔離必須先成為產品需求，而不能只靠現有 API。

**Considered Options**

- 現在加入應用層認證與多使用者模型：安全邊界較完整，但超出目前單一使用者、私有網路的需求。
- 以私有網路作為 MVP 邊界：部署簡單且符合目前使用方式，因此採用。
