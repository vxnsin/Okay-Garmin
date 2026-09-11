"""Spotify Web API client.

Authorisation uses the PKCE flow, so no client secret is needed and none has
to be shipped inside the application. The user creates their own app in the
Spotify developer dashboard and pastes its client ID into the settings.

Two things worth knowing, both surfaced in the UI:

  * Starting playback is a Premium-only endpoint. Search and "what is playing"
    work on a free account; "play this song" returns 403.
  * Playback is sent to whichever device is currently active, so Spotify has
    to be running somewhere.

Tokens are kept in %APPDATA%\\Okay-Garmin\\spotify.json, separate from
config.json so the settings file stays safe to share when reporting a bug.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import requests

from .logging_setup import get_logger
from .paths import data_dir

log = get_logger("spotify")

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"

REDIRECT_PORT = 8888
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback"

SCOPES = " ".join(
    [
        "user-read-playback-state",
        "user-modify-playback-state",
        "user-read-currently-playing",
    ]
)

# What "spiel {}" should look for, in order of preference.
SEARCH_TYPES = ("track", "album", "playlist", "artist")

_CLOSE_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Okay-Garmin</title><style>
body{font-family:'Segoe UI',system-ui,sans-serif;background:#101016;color:#f4f4f6;
display:grid;place-items:center;height:100vh;margin:0}
div{text-align:center}h1{font-size:20px;font-weight:600}
p{color:#9ca3b0;font-size:14px;margin-top:8px}
</style></head><body><div><h1>%s</h1><p>%s</p></div></body></html>"""


class SpotifyError(Exception):
    """Raised for failures worth showing the user."""


def _token_path():
    return data_dir() / "spotify.json"


def _make_verifier() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


class _CallbackHandler(BaseHTTPRequestHandler):
    """Catches the one redirect Spotify sends back after the user approves."""

    result: dict[str, str] = {}

    def do_GET(self) -> None:  # noqa: N802 -- name required by BaseHTTPRequestHandler
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)

        if "code" in params:
            _CallbackHandler.result = {"code": params["code"][0], "state": params.get("state", [""])[0]}
            body = _CLOSE_PAGE % ("Connected to Spotify", "You can close this tab.")
        else:
            _CallbackHandler.result = {"error": params.get("error", ["unknown"])[0]}
            body = _CLOSE_PAGE % ("Connection failed", _CallbackHandler.result["error"])

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *args) -> None:
        return  # keep the console clean


class SpotifyClient:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: dict[str, Any] = self._load_tokens()
        self._session = requests.Session()

    # ------------------------------------------------------------------ tokens

    def _load_tokens(self) -> dict[str, Any]:
        path = _token_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not read Spotify tokens: %s", exc)
            return {}

    def _save_tokens(self) -> None:
        path = _token_path()
        try:
            path.write_text(json.dumps(self._tokens, indent=2), encoding="utf-8")
        except OSError as exc:
            log.error("Could not save Spotify tokens: %s", exc)

    def _store(self, payload: dict, client_id: str) -> None:
        with self._lock:
            self._tokens = {
                "client_id": client_id,
                "access_token": payload["access_token"],
                # A refresh response may omit refresh_token; keep the old one.
                "refresh_token": payload.get("refresh_token")
                or self._tokens.get("refresh_token"),
                "expires_at": time.time() + payload.get("expires_in", 3600) - 60,
            }
        self._save_tokens()

    @property
    def connected(self) -> bool:
        return bool(self._tokens.get("refresh_token"))

    def disconnect(self) -> None:
        with self._lock:
            self._tokens = {}
        _token_path().unlink(missing_ok=True)
        log.info("Spotify disconnected")

    # ------------------------------------------------------------------ auth

    def authorize(self, client_id: str, timeout: float = 180.0) -> None:
        """Run the PKCE flow. Blocks until the user approves or it times out."""
        client_id = (client_id or "").strip()
        if not client_id:
            raise SpotifyError("no-client-id")

        verifier, challenge = _make_verifier()
        state = secrets.token_urlsafe(16)
        _CallbackHandler.result = {}

        try:
            server = HTTPServer(("127.0.0.1", REDIRECT_PORT), _CallbackHandler)
        except OSError as exc:
            raise SpotifyError(f"port-busy: {exc}") from exc

        server.timeout = timeout
        params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "scope": SCOPES,
            "state": state,
        }
        webbrowser.open(f"{AUTH_URL}?{urllib.parse.urlencode(params)}")

        try:
            # One request is all we need; handle_request honours server.timeout.
            server.handle_request()
        finally:
            server.server_close()

        result = _CallbackHandler.result
        if not result:
            raise SpotifyError("timeout")
        if "error" in result:
            raise SpotifyError(result["error"])
        if result.get("state") != state:
            # Someone else's redirect hit our port.
            raise SpotifyError("state-mismatch")

        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": result["code"],
                "redirect_uri": REDIRECT_URI,
                "client_id": client_id,
                "code_verifier": verifier,
            },
            timeout=15,
        )
        if response.status_code != 200:
            raise SpotifyError(f"token-exchange-failed: {response.text[:200]}")

        self._store(response.json(), client_id)
        log.info("Spotify connected")

    def _refresh(self) -> None:
        refresh_token = self._tokens.get("refresh_token")
        client_id = self._tokens.get("client_id")
        if not (refresh_token and client_id):
            raise SpotifyError("not-connected")

        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            },
            timeout=15,
        )
        if response.status_code != 200:
            # The grant was revoked or expired -- make the UI show "connect" again.
            self.disconnect()
            raise SpotifyError("refresh-failed")
        self._store(response.json(), client_id)

    def _auth_header(self) -> dict[str, str]:
        if not self.connected:
            raise SpotifyError("not-connected")
        if time.time() >= self._tokens.get("expires_at", 0):
            self._refresh()
        return {"Authorization": f"Bearer {self._tokens['access_token']}"}

    # ------------------------------------------------------------------ requests

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        headers = self._auth_header()
        headers.update(kwargs.pop("headers", {}))
        response = self._session.request(
            method, f"{API}{path}", headers=headers, timeout=12, **kwargs
        )

        if response.status_code == 401:
            # Token died early; one retry with a fresh one.
            self._refresh()
            headers = self._auth_header()
            response = self._session.request(
                method, f"{API}{path}", headers=headers, timeout=12, **kwargs
            )

        if response.status_code == 403:
            raise SpotifyError("premium-required")
        if response.status_code == 404:
            raise SpotifyError("no-active-device")
        return response

    # ------------------------------------------------------------------ actions

    def search(self, query: str, types: tuple[str, ...] = SEARCH_TYPES) -> dict | None:
        """Find the best match for a spoken query.

        Spotify returns each type in its own bucket with no cross-type ranking,
        so the first hit of the earliest requested type wins -- which is why
        SEARCH_TYPES puts tracks before artists.
        """
        response = self._request(
            "GET",
            "/search",
            params={"q": query, "type": ",".join(types), "limit": 3, "market": "from_token"},
        )
        if response.status_code != 200:
            raise SpotifyError(f"search-failed: {response.status_code}")

        payload = response.json()
        for kind in types:
            items = (payload.get(f"{kind}s") or {}).get("items") or []
            items = [item for item in items if item]
            if items:
                return self._describe(items[0], kind)
        return None

    @staticmethod
    def _describe(item: dict, kind: str) -> dict:
        images = item.get("images") or (item.get("album") or {}).get("images") or []
        artists = item.get("artists") or []
        if kind == "playlist":
            subtitle = (item.get("owner") or {}).get("display_name", "Playlist")
        elif artists:
            subtitle = ", ".join(a.get("name", "") for a in artists[:2])
        else:
            subtitle = kind.capitalize()

        return {
            "uri": item.get("uri"),
            "kind": kind,
            "title": item.get("name", ""),
            "subtitle": subtitle,
            # images are ordered widest first; the middle one is plenty for a HUD
            "image": (images[min(1, len(images) - 1)].get("url") if images else None),
        }

    def play(self, query: str) -> dict:
        """Search for `query` and start playing the best match."""
        match = self.search(query)
        if match is None:
            raise SpotifyError("nothing-found")

        body = (
            {"uris": [match["uri"]]}
            if match["kind"] == "track"
            else {"context_uri": match["uri"]}
        )
        response = self._request("PUT", "/me/player/play", json=body)
        if response.status_code not in (200, 202, 204):
            raise SpotifyError(f"play-failed: {response.status_code}")

        log.info("Spotify playing %s %r", match["kind"], match["title"])
        return match

    def control(self, action: str) -> None:
        """pause / resume / next / previous / shuffle."""
        endpoints = {
            "pause": ("PUT", "/me/player/pause"),
            "resume": ("PUT", "/me/player/play"),
            "next": ("POST", "/me/player/next"),
            "previous": ("POST", "/me/player/previous"),
        }
        if action not in endpoints:
            raise SpotifyError(f"unknown-action: {action}")

        method, path = endpoints[action]
        response = self._request(method, path)
        if response.status_code not in (200, 202, 204):
            raise SpotifyError(f"{action}-failed: {response.status_code}")

    def now_playing(self) -> dict | None:
        """What is playing right now, shaped like a search result."""
        response = self._request("GET", "/me/player/currently-playing")
        if response.status_code == 204 or not response.content:
            return None
        if response.status_code != 200:
            raise SpotifyError(f"now-playing-failed: {response.status_code}")

        item = (response.json() or {}).get("item")
        if not item:
            return None
        return self._describe(item, "track")

    def status(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "client_id": self._tokens.get("client_id", ""),
        }
