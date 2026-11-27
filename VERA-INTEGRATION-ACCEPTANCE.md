# VERA v0.3.0 formal integration acceptance
Baseline: 933a6adb1f8db9450cbfdfc2745e709f16a6160b.
This branch never deploys Render. The workflow probes public health and unauthenticated GET boundaries without any secret or personal data.
## Required external handoff
- Publish the existing Sites candidate as private, using its own authenticated owner identity; do not expose raw task data publicly.
- Store a new high-entropy source token only in the Sites server secret store, and its SHA-256 hex digest in the existing Render service. Never commit or paste the raw token in chat. Keep the owner token separate.
- Install and authorize the formal plugin, confirm the eight tool names and distinguish it from the synthetic QA plugin.
- First verify list/read; then create a synthetic task with stable source_id, verify idempotency, cancel it, and verify no real call is triggered.
- Source task publication currently does not schedule calls. Owner-authorized call scheduling remains separate. An automatic policy must be explicitly enabled by the owner and enforce device selection, Asia/Taipei 10:00–24:00, deduplication, retry limits, cancellation and off switch before any unattended calls.
- Existing automation: daily 12:00 and 21:00 Asia/Taipei. Do not create a duplicate. Enable formal writes only after authorization and actual test evidence. Read results by consumer cursor and acknowledge after durable processing.
- Keep current Android install until backup and signer migration acceptance. GitHub debug artifact is not a formal signed update.
