from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib import error, parse, request
from uuid import uuid4

from dotenv import dotenv_values, set_key


GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"


class GitHubAuthError(RuntimeError):
    pass


class GitHubDeviceAuth:
    def __init__(
        self,
        client_id: str | None,
        env_path: Path,
        app_slug: str | None = None,
    ) -> None:
        self.client_id = client_id
        self.env_path = env_path
        self.app_slug = app_slug if app_slug and app_slug.replace("-", "").isalnum() else None
        self._device_sessions: dict[str, dict[str, object]] = {}

    @property
    def configured(self) -> bool:
        return bool(self.client_id)

    def status(self) -> dict[str, object]:
        if not self.configured:
            return {
                "configured": False,
                "connected": False,
                "message": "GitHub App authorization is not configured.",
            }

        try:
            token = self.get_token()
        except GitHubAuthError as exc:
            return {
                "configured": True,
                "connected": False,
                "message": str(exc),
            }
        if not token:
            return {
                "configured": True,
                "connected": False,
                "message": "Connect GitHub to authorize repository pushes and pull requests.",
                "install_url": self._install_url(),
            }
        if os.getenv("GITHUB_AUTH_METHOD") != "github_app":
            return {
                "configured": True,
                "connected": False,
                "message": "A personal access token is configured. Connect the GitHub App here to authorize access without manual token setup.",
                "install_url": self._install_url(),
            }

        return {
            "configured": True,
            "connected": True,
            "message": "GitHub is connected. Authorized repositories can receive repair branches and pull requests.",
            "install_url": self._install_url(),
        }

    def start(self) -> dict[str, object]:
        self._require_configuration()
        response_data = self._post_form(
            GITHUB_DEVICE_CODE_URL,
            {"client_id": self.client_id or ""},
        )
        if response_data.get("error"):
            raise GitHubAuthError(self._oauth_error(response_data))

        required = ("device_code", "user_code", "verification_uri")
        if any(not response_data.get(key) for key in required):
            raise GitHubAuthError("GitHub returned an incomplete device authorization response.")

        interval = max(int(response_data.get("interval", 5)), 1)
        expires_in = max(int(response_data.get("expires_in", 900)), 1)
        session_id = uuid4().hex
        self._device_sessions[session_id] = {
            "device_code": str(response_data["device_code"]),
            "interval": interval,
            "expires_at": time.monotonic() + expires_in,
            "next_poll_at": 0.0,
        }
        return {
            "session_id": session_id,
            "user_code": response_data["user_code"],
            "verification_uri": response_data["verification_uri"],
            "expires_in": expires_in,
            "interval": interval,
            "install_url": self._install_url(),
        }

    def poll(self, session_id: str) -> dict[str, object]:
        self._require_configuration()
        session = self._device_sessions.get(session_id)
        if session is None:
            raise GitHubAuthError("This GitHub authorization has expired. Start again.")

        now = time.monotonic()
        expires_at = float(session["expires_at"])
        if now >= expires_at:
            self._device_sessions.pop(session_id, None)
            raise GitHubAuthError("The GitHub authorization code expired. Start again.")

        interval = int(session["interval"])
        next_poll_at = float(session["next_poll_at"])
        if now < next_poll_at:
            return {
                "authorized": False,
                "pending": True,
                "retry_after": max(1, int(next_poll_at - now + 0.99)),
            }

        session["next_poll_at"] = now + interval
        response_data = self._post_form(
            GITHUB_ACCESS_TOKEN_URL,
            {
                "client_id": self.client_id or "",
                "device_code": str(session["device_code"]),
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )

        oauth_error = response_data.get("error")
        if oauth_error == "authorization_pending":
            return {
                "authorized": False,
                "pending": True,
                "retry_after": interval,
            }
        if oauth_error == "slow_down":
            interval += 5
            session["interval"] = interval
            session["next_poll_at"] = time.monotonic() + interval
            return {
                "authorized": False,
                "pending": True,
                "retry_after": interval,
            }
        if oauth_error in {"access_denied", "expired_token"}:
            self._device_sessions.pop(session_id, None)
            raise GitHubAuthError(self._oauth_error(response_data))
        if oauth_error:
            self._device_sessions.pop(session_id, None)
            raise GitHubAuthError(self._oauth_error(response_data))

        access_token = response_data.get("access_token")
        if not access_token:
            raise GitHubAuthError("GitHub did not return an access token.")

        self._save_tokens(response_data)
        self._device_sessions.pop(session_id, None)
        return {
            "authorized": True,
            "message": "GitHub connected. You can now push repair branches and create pull requests in repositories where the GitHub App is installed.",
        }

    def get_token(self) -> str | None:
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            return None

        expires_at = os.getenv("GITHUB_TOKEN_EXPIRES_AT")
        if not expires_at:
            return token

        try:
            remaining = float(expires_at) - time.time()
        except ValueError as exc:
            raise GitHubAuthError(
                "The saved GitHub token expiry is invalid. Reconnect GitHub."
            ) from exc

        if remaining > 60:
            return token

        refresh_token = os.getenv("GITHUB_REFRESH_TOKEN")
        if not refresh_token:
            raise GitHubAuthError(
                "The GitHub authorization expired. Reconnect GitHub to continue."
            )

        self._require_configuration()
        response_data = self._post_form(
            GITHUB_ACCESS_TOKEN_URL,
            {
                "client_id": self.client_id or "",
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if response_data.get("error") or not response_data.get("access_token"):
            raise GitHubAuthError(
                "Could not renew GitHub access. Reconnect GitHub to continue. "
                + self._oauth_error(response_data)
            )

        self._save_tokens(response_data)
        return str(response_data["access_token"])

    def _save_tokens(self, response_data: dict[str, object]) -> None:
        access_token = str(response_data["access_token"])
        set_key(str(self.env_path), "GITHUB_TOKEN", access_token, quote_mode="always")
        os.environ["GITHUB_TOKEN"] = access_token
        set_key(
            str(self.env_path),
            "GITHUB_AUTH_METHOD",
            "github_app",
            quote_mode="always",
        )
        os.environ["GITHUB_AUTH_METHOD"] = "github_app"

        refresh_token = response_data.get("refresh_token")
        if refresh_token:
            refresh_value = str(refresh_token)
            set_key(
                str(self.env_path),
                "GITHUB_REFRESH_TOKEN",
                refresh_value,
                quote_mode="always",
            )
            os.environ["GITHUB_REFRESH_TOKEN"] = refresh_value
        else:
            self._remove_saved_token("GITHUB_REFRESH_TOKEN")

        expires_in = response_data.get("expires_in")
        if expires_in is not None:
            expiry = str(time.time() + int(expires_in))
            set_key(
                str(self.env_path),
                "GITHUB_TOKEN_EXPIRES_AT",
                expiry,
                quote_mode="always",
            )
            os.environ["GITHUB_TOKEN_EXPIRES_AT"] = expiry
        else:
            self._remove_saved_token("GITHUB_TOKEN_EXPIRES_AT")

        refresh_expires_in = response_data.get("refresh_token_expires_in")
        if refresh_expires_in is not None:
            refresh_expiry = str(time.time() + int(refresh_expires_in))
            set_key(
                str(self.env_path),
                "GITHUB_REFRESH_TOKEN_EXPIRES_AT",
                refresh_expiry,
                quote_mode="always",
            )
            os.environ["GITHUB_REFRESH_TOKEN_EXPIRES_AT"] = refresh_expiry
        else:
            self._remove_saved_token("GITHUB_REFRESH_TOKEN_EXPIRES_AT")

    def _remove_saved_token(self, key: str) -> None:
        if self.env_path.exists():
            values = dotenv_values(self.env_path)
            if values.get(key) is not None:
                set_key(str(self.env_path), key, "", quote_mode="always")
        os.environ.pop(key, None)

    def _require_configuration(self) -> None:
        if not self.configured:
            raise GitHubAuthError(
                "GitHub App authorization is not configured. Set GITHUB_APP_CLIENT_ID in the local .env."
            )

    def _install_url(self) -> str | None:
        if not self.app_slug:
            return None
        return f"https://github.com/apps/{self.app_slug}/installations/new"

    @staticmethod
    def _post_form(url: str, values: dict[str, str]) -> dict[str, object]:
        body = parse.urlencode(values).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "CICD-Healing-Agent",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=15) as response:
                payload = response.read()
        except error.HTTPError as exc:
            payload = exc.read()
        except error.URLError as exc:
            raise GitHubAuthError(
                f"Could not connect to GitHub: {exc.reason}"
            ) from exc

        try:
            result = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise GitHubAuthError("GitHub returned an unreadable authorization response.") from exc
        if not isinstance(result, dict):
            raise GitHubAuthError("GitHub returned an invalid authorization response.")
        return result

    @staticmethod
    def _oauth_error(response_data: dict[str, object]) -> str:
        error_code = str(response_data.get("error", ""))
        descriptions = {
            "authorization_pending": "Waiting for GitHub authorization.",
            "access_denied": "GitHub authorization was denied.",
            "expired_token": "The GitHub authorization code expired. Start again.",
            "incorrect_client_credentials": "The GitHub App client ID is invalid.",
            "unsupported_grant_type": "GitHub rejected the device authorization grant.",
        }
        return descriptions.get(
            error_code,
            str(response_data.get("error_description") or "GitHub authorization failed."),
        )
