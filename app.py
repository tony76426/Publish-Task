"""VERA Nexus entry point; gate the first production v0.3 database migration."""
import os

if __name__ == '__main__':
    if os.getenv("RENDER") or os.getenv("VERA_PUSH_DB") == "/var/data/vera-push.sqlite3":
        try:
            from vera_release_gate import production_release_gate
            production_release_gate()
        except Exception as exc:
            print("VERA v0.3 release gate: FAILED (" + type(exc).__name__ + ")", flush=True)
            raise SystemExit(1)
    os.execvp('gunicorn', ['gunicorn', '--bind', '0.0.0.0:' + os.getenv('PORT', '10000'), 'vera_app:app'])
else:
    from vera_app import app
