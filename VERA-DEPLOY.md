# VERA connectivity prototype

Existing Publish-Task service: switch branch to vera-mvp, build command: `pip install -r requirements-vera.txt`, start command: `gunicorn vera_app:app`, health check: /health. Keep original main branch unchanged. Do not merge this branch automatically. Reverting the settings restores the original application.

Set OPENAI_API_KEY securely in Render Environment and generate a separate long random VERA_ACCESS_TOKEN. The latter is required in the Authorization bearer header; never embed it in a distributed APK. No secrets in GitHub. Existing repository is public. Do not commit private data.

GET /health checks availability. POST /api/realtime/client-secret creates an ephemeral OpenAI Realtime credential for an authenticated client. Real audio and billing must be tested after credentials are configured. Gmail, durable cloud memory and cloud scheduling are outside this push integration. The shared bearer is for one private operator, not multi-user enrollment.

## Firebase Cloud Messaging

- Firebase project: `vera-nexus-e5119` (Spark). Android package: `tw.vera.nexus`. Firebase app ID: `1:1041608787597:android:e26a9db3e9039b2cd244c4`.
- Supply the registered app's Android client SDK config as `android/app/google-services.json`. The file is ignored by Git and the build rejects a mismatched project or app. A build without the file preserves local reminders and reports unavailable Firebase push.
- In the existing Vera Nexus Render service, store the Google send credential as a **secret file** named `vera-firebase.json`. Set `GOOGLE_APPLICATION_CREDENTIALS` to `/etc/secrets/vera-firebase.json`. Use a dedicated service account scoped to sending FCM for this project. Do not paste the credential into the repository, logs, APK or chat.
- If an existing persistent disk is available, set `VERA_PUSH_DB` to a path on that disk. Without a disk, the SQLite registry survives worker restarts on the same instance but can be lost on redeploy. Reopening the opted-in app registers the current device token again. Keep the service single-instance unless the registry is migrated to shared storage.
- All four push operations require the existing VERA bearer. `POST /api/push/status` checks whether Render sees a credential file. `PUT /api/push/device` enrolls or rotates a device token. `DELETE /api/push/device` revokes an installation. `POST /api/push/dispatch` takes UUIDv4 `device_id` and `event_id`, optional `task_id` (opaque local task identifier) and optional `test`. Do not send legal case content through push. The 45-second message expiry, 24-hour server retry guard and device-side deduplication prevent stale or duplicate alerts within this prototype's storage limits.
- With a configured build and working private login, allow Android notifications, then choose **設定 → 啟用並測試 Firebase 推播**. A 202 response means Google accepted the send. Verify that the phone actually rings and that accepting a test does not start the microphone. Repeat while the app is backgrounded, and check that quiet hours and **停用遠端推播** suppress the alert.
