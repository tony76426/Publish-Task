"""Offer upgrades only from a published, signer-pinned VERA release."""

import os
import re
import time

import requests
from flask import jsonify

REPOSITORY = "https://github.com/tony76426/Publish-Task"
RELEASES = "https://api.github.com/repos/tony76426/Publish-Task/releases"
TAG = re.compile(r"vera-nexus-v([0-9]+\.[0-9]+\.[0-9]+)-fcm-[0-9]+-r[0-9]+")
SHA = re.compile(r"[a-f0-9]{64}")
_cached = (None, 0, None)


def release_info(expected):
    response = requests.get(RELEASES, params={"per_page": 20}, timeout=4)
    response.raise_for_status()
    for release in response.json():
        tag = release.get("tag_name", "")
        match = TAG.fullmatch(tag)
        if not match or release.get("draft") or release.get("prerelease"):
            continue
        assets = {asset["name"]: asset for asset in release.get("assets", [])}
        proof = assets.get("vera-release.json")
        apk = assets.get("VERA-Nexus.apk")
        if not proof or not apk or not 0 < proof.get("size", 0) <= 4096:
            continue
        base = REPOSITORY + "/releases/download/" + tag
        manifest = requests.get(base + "/vera-release.json", timeout=4)
        manifest.raise_for_status()
        if len(manifest.content) > 4096:
            continue
        value = manifest.json()
        if (value.get("version") != match[1] or value.get("package") != "tw.vera.nexus"
                or type(value.get("version_code")) is not int or value["version_code"] < 10
                or value.get("firebase") is not True or value.get("signer_sha256") != expected
                or not SHA.fullmatch(value.get("apk_sha256", ""))
                or apk.get("digest") != "sha256:" + value["apk_sha256"]):
            continue
        return {"available": True, "tag": tag, "version": match[1], "version_code": value["version_code"],
                "sha256": value["apk_sha256"], "android_firebase": True, "url": base + "/VERA-Nexus.apk"}
    return {"available": False}


def upgrade_status():
    global _cached
    expected = os.getenv("VERA_RELEASE_CERT_SHA256", "").lower()
    if not SHA.fullmatch(expected):
        return jsonify(available=False)
    key, expires, result = _cached
    now = time.monotonic()
    if key == expected and expires > now:
        return jsonify(result)
    try:
        result = release_info(expected)
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        return jsonify(error="暫時無法驗證新版 APK"), 503
    _cached = (expected, now + 120, result)
    return jsonify(result)
