import os
import hmac
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

def authorized():
    secret = os.getenv("VERA_ACCESS_TOKEN", "")
    return bool(secret) and hmac.compare_digest(request.headers.get("Authorization", "").encode(), ("Bearer " + secret).encode())

@app.get("/")
@app.get("/health")
def health():
    return jsonify(service="VERA", status="ok")

@app.post("/api/realtime/client-secret")
def client_secret():
    if not authorized():
        return jsonify(error="unauthorized"), 401
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return jsonify(error="OpenAI API key is not configured"), 503
    try:
        response = requests.post(
            "https://api.openai.com/v1/realtime/client_secrets",
            headers={"Authorization": "Bearer " + key},
            json={"session": {"type": "realtime", "model": os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime"), "instructions": "你是 VERA，一位使用繁體中文的個人語音秘書。確認使用者指示，不要假稱已執行工作。"}},
            timeout=20
        )
        if not response.ok:
            return jsonify(error="Realtime session setup failed", upstream_status=response.status_code), 502
        result = jsonify(response.json())
        result.headers["Cache-Control"] = "no-store"
        return result
    except (requests.RequestException, ValueError):
        return jsonify(error="Realtime service unavailable"), 502
