"""VERA Nexus v0.2.1 entry point; checkpoint only, no schema or API changes."""
import os

if __name__ == '__main__':
    try:
        from vera_preupgrade import production_checkpoint
        production_checkpoint()
    except Exception as exc:
        print("VERA pre-v030 checkpoint: FAILED (" + type(exc).__name__ + ")", flush=True)
    print("VERA v0.3 config readiness: data_key=" + ("present" if os.getenv("VERA_DATA_KEY") else "missing")
          + "; work_token_hash=" + ("present" if os.getenv("VERA_WORK_TOKEN_SHA256") else "missing"), flush=True)
    os.execvp('gunicorn', ['gunicorn', '--bind', '0.0.0.0:' + os.getenv('PORT', '10000'), 'vera_app:app'])
else:
    from vera_app import app
