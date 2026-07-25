# Use polling for MVP completion notification

**Status: accepted**

The MVP does not send email, webhook, WebSocket, or other push notifications. Callers discover completion, failure, and cancellation by polling the job detail or list endpoints. This fits the single-user private-network deployment and avoids introducing SMTP credentials, notification retry/idempotency, and externally reachable result links before another integration requires them.

**Considered Options**

- Email or webhook notifications: useful for hands-off integrations, but requires a separate notification subsystem and a clear access model for result links.
- Polling: already supported by the job API and sufficient for the current workflow, therefore adopted.
