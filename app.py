"""VERA Nexus entry point; original Publish-Task remains on main."""
import os
from vera_app import app

if __name__ == '__main__':
    os.execvp('gunicorn', ['gunicorn', '--bind', '0.0.0.0:' + os.getenv('PORT', '10000'), 'vera_app:app'])
