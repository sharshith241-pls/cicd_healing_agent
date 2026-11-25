import os
import json
import time

from backend.github_auth import GitHubDeviceAuth


class FakeResponse:
    def __init__(self, value):
        self.payload = json.dumps(value).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return self.payload


def _fake_urlopen(responses):
    def open_request(req, timeout):
        assert timeout == 15
        assert req.get_header("Accept") == "application/json"
        return FakeResponse(responses.pop(0))

    return open_request


def test_device_authorization_saves_token_only_after_user_approval(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "backend.github_auth.request.urlopen",
        _fake_urlopen(
            [
                {
                    "device_code": "private-device-code",
                    "user_code": "ABCD-EFGH",
                    "verification_uri": "https://github.com/login/device",
                    "interval": 1,
                    "expires_in": 600,
                },
                {"error": "authorization_pending"},
                {
                    "access_token": "ghu_access",
                    "refresh_token": "ghr_refresh",
                    "expires_in": 28800,
                    "refresh_token_expires_in": 15897600,
                },
            ]
        ),
    )
    env_path = tmp_path / ".env"
    auth = GitHubDeviceAuth("public-client-id", env_path, "cicd-healing-agent")

    device = auth.start()
    assert device["user_code"] == "ABCD-EFGH"
    assert device["install_url"] == (
        "https://github.com/apps/cicd-healing-agent/installations/new"
    )
    assert auth.poll(str(device["session_id"]))["pending"] is True
    auth._device_sessions[str(device["session_id"])]["next_poll_at"] = 0
    result = auth.poll(str(device["session_id"]))

    assert result["authorized"] is True
    assert "ghu_access" not in result
    assert os.environ["GITHUB_AUTH_METHOD"] == "github_app"
    saved = env_path.read_text(encoding="utf-8")
    assert "GITHUB_TOKEN='ghu_access'" in saved
    assert "GITHUB_REFRESH_TOKEN='ghr_refresh'" in saved


def test_expired_access_token_is_refreshed_and_rotated(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "old-access")
    monkeypatch.setenv("GITHUB_REFRESH_TOKEN", "old-refresh")
    monkeypatch.setenv("GITHUB_TOKEN_EXPIRES_AT", str(time.time() - 1))
    monkeypatch.setattr(
        "backend.github_auth.request.urlopen",
        _fake_urlopen(
            [
                {
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "expires_in": 28800,
                    "refresh_token_expires_in": 15897600,
                }
            ]
        ),
    )
    env_path = tmp_path / ".env"
    env_path.write_text(
        "GITHUB_TOKEN='old-access'\nGITHUB_REFRESH_TOKEN='old-refresh'\n",
        encoding="utf-8",
    )
    auth = GitHubDeviceAuth("public-client-id", env_path)

    assert auth.get_token() == "new-access"
    saved = env_path.read_text(encoding="utf-8")
    assert "GITHUB_TOKEN='new-access'" in saved
    assert "GITHUB_REFRESH_TOKEN='new-refresh'" in saved


def test_status_requires_app_configuration_and_connected_token(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    auth = GitHubDeviceAuth(None, tmp_path / ".env")

    assert auth.status() == {
        "configured": False,
        "connected": False,
        "message": "GitHub App authorization is not configured.",
    }


def test_personal_token_does_not_count_as_github_app_authorization(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("GITHUB_TOKEN", "fine-grained-personal-token")
    monkeypatch.delenv("GITHUB_TOKEN_EXPIRES_AT", raising=False)
    monkeypatch.delenv("GITHUB_AUTH_METHOD", raising=False)
    auth = GitHubDeviceAuth("public-client-id", tmp_path / ".env")

    status = auth.status()

    assert status["configured"] is True
    assert status["connected"] is False
    assert "personal access token is configured" in status["message"]
