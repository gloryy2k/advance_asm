"""Container startup: migrate first. Nuclei templates are no longer refreshed here (a blocking download before the server
starts); the server updates them in the background when asked (BBASM_UPDATE_TEMPLATES) and the Tools page shows the result."""
from backend.config import Settings
from backend.db import Database


def bootstrap(settings=None, run=None):
    settings = settings or Settings()
    Database(settings.BBASM_DATA / "bbasm.db").migrate()


if __name__ == "__main__":
    bootstrap()
