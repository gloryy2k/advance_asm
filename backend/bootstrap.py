"""Container startup: migrate first, then bounded audited template refresh."""
import logging
import os
import shutil
import subprocess

from backend.config import Settings
from backend.db import Database
from backend.scope_gate import audit


def bootstrap(settings=None, run=subprocess.run):
    settings = settings or Settings()
    Database(settings.BBASM_DATA / "bbasm.db").migrate()
    binary = shutil.which("nuclei", path=settings.tool_search_path())
    if binary and os.environ.get("BBASM_UPDATE_TEMPLATES", "1") == "1":
        audit(settings.BBASM_DATA / "audit.jsonl", "nuclei-templates", "allow", "template_update")
        try:
            result = run([binary, "-update-templates", "-silent"], timeout=120, check=False,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if result.returncode:
                logging.getLogger("bbasm").warning("Template update failed; using installed cache")
        except (OSError, subprocess.TimeoutExpired):
            logging.getLogger("bbasm").warning("Template update unavailable; continuing")


if __name__ == "__main__":
    bootstrap()
