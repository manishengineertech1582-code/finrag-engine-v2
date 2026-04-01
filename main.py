"""
Convenience launcher for local backend development.

Prefer the explicit uvicorn command from the root README for production and
for cases where you want full control over workers or reload behavior.
"""

import os

import uvicorn


def main() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("APP_ENV", "development").lower() == "development"

    uvicorn.run("app.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
