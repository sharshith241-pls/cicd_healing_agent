"""Start the opt-in local API that runs jobs using this computer's Docker."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import uvicorn
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")
os.environ["CICD_LOCAL_RUNNER"] = "1"

from backend.main import app  # noqa: E402


class PrivateNetworkAccessMiddleware:
    """Allow browser preflights from the configured HTTPS UI to loopback."""

    def __init__(self, application: Any) -> None:
        self.application = application

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.application(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        allow_private_network = (
            headers.get(b"access-control-request-private-network") == b"true"
        )

        async def send_with_private_network(message: dict) -> None:
            if allow_private_network and message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                if not any(
                    name.lower() == b"access-control-allow-private-network"
                    for name, _ in response_headers
                ):
                    response_headers.append(
                        (b"access-control-allow-private-network", b"true")
                    )
                message["headers"] = response_headers
            await send(message)

        await self.application(scope, receive, send_with_private_network)


if __name__ == "__main__":
    print("Local Docker runner listening at http://127.0.0.1:8765")
    print("Keep this process running while using the website's local Docker mode.")
    uvicorn.run(
        PrivateNetworkAccessMiddleware(app),
        host="127.0.0.1",
        port=8765,
        log_level="info",
    )
