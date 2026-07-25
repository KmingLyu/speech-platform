# Recover stale jobs through bounded retry

**Status: accepted**

Workers must maintain a heartbeat while processing. If a job's heartbeat exceeds the configured stale timeout, the system treats the worker loss as a transient failure: it requeues the job while attempts remain, then marks it `failed` with a worker-loss error after the retry limit. A `cancel_requested` job must not be silently requeued by recovery. This prevents jobs from remaining permanently stuck in `processing` while preserving the bounded-retry decision.

**Considered Options**

- Leave stale jobs for manual intervention: simple, but violates the asynchronous reliability goal and can strand work indefinitely.
- Requeue stale jobs without a limit: can create an infinite failure loop after a systemic outage.
- Heartbeat-based recovery with bounded retry: recovers transient worker loss without unbounded retries, therefore adopted.
