# VERA connectivity prototype

Existing Publish-Task service: switch branch to vera-mvp, build command: `pip install -r requirements-vera.txt`, start command: `gunicorn vera_app:app`, health check: /health. Keep original main branch unchanged. Do not merge this branch automatically. Reverting the settings restores the original application.

Set OPENAI_API_KEY securely in Render Environment and generate a separate long random VERA_ACCESS_TOKEN. The latter is required in the Authorization bearer header; never embed it in a distributed APK. No secrets in GitHub. Existing repository is public. Do not commit private data.

GET /health checks availability. POST /api/realtime/client-secret creates an ephemeral OpenAI Realtime credential for an authenticated client. Real audio and billing must be tested after credentials are configured. This is a connectivity prototype, not a finished assistant: FCM, Android, Gmail bridge, persistent memory and scheduling are not implemented. A public deployment requires secure user enrollment, rate limits and abuse monitoring before general use.
