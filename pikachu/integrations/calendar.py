"""
pikachu/integrations/calendar.py
──────────────────────────────────
Google Calendar integration — privacy-first design.

HOW AUTHENTICATION WORKS (important):
──────────────────────────────────────
Pikachu NEVER sees or stores your Google password.

  1. First run: your browser opens → you log in directly to Google
  2. Google asks: "Allow Pikachu to manage your Calendar?" → you click Allow
  3. Google gives Pikachu a refresh token
  4. That token is stored ONLY in Windows Credential Manager
     (the same encrypted vault that holds your Wi-Fi passwords)
     NO FILES are written to disk — not even encrypted ones.
  5. Every future run: Pikachu silently exchanges the token for a short-lived
     access token, entirely in memory. No browser, no login.

Data flow:
  Google Credential Manager (Windows)
       ↓  refresh_token (string, ~150 chars)
  Memory only (access_token, expires in 1 hour, auto-refreshed)
       ↓
  Google Calendar API calls (HTTPS)

Nothing is ever written to a file on your disk.
"""

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import requests

from pikachu.utils.logger import get_logger
from pikachu import config as cfg

log = get_logger(__name__)

# ── Keyring keys ──────────────────────────────────────────────────────────────
_KEYRING_SERVICE       = "LivingDesktopPet"
_KEYRING_REFRESH_TOKEN = "gcal_refresh_token"
_KEYRING_CLIENT_ID     = "gcal_client_id"
_KEYRING_CLIENT_SECRET = "gcal_client_secret"

# ── Google OAuth2 endpoints ───────────────────────────────────────────────────
_AUTH_URL    = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL   = "https://oauth2.googleapis.com/token"
_REVOKE_URL  = "https://oauth2.googleapis.com/revoke"
_CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"

_SCOPES = " ".join(cfg.CALENDAR_SCOPES)


class CalendarService:
    """
    Google Calendar service with privacy-first token management.

    Tokens are held in memory and in Windows Credential Manager only.
    No files are ever written to disk.

    Usage:
        svc = CalendarService()
        if not svc.is_authenticated():
            svc.authenticate()           # opens browser once
        events = svc.list_upcoming(days=3)
        svc.create_event("Meeting", "2026-06-10", "14:00", "15:00")
    """

    def __init__(self):
        self._access_token:  Optional[str] = None
        self._token_expiry:  Optional[datetime] = None
        self._refresh_token: Optional[str] = None
        self._client_id:     Optional[str] = None
        self._client_secret: Optional[str] = None
        self._lock = threading.Lock()

        # Load credentials and refresh token from Credential Manager (if present)
        self._load_from_keyring()

    # ── Authentication ────────────────────────────────────────────────────────

    def is_authenticated(self) -> bool:
        """True if we have a refresh token stored (can get access tokens silently)."""
        return bool(self._refresh_token)

    def authenticate(self, client_id: str = None, client_secret: str = None):
        """
        Run the OAuth2 "installed app" flow.

        If client_id / client_secret are passed, they are stored in Windows
        Credential Manager for future runs (so you never need to pass them again).

        Opens the user's default browser to Google's login page.
        After the user authorises, the browser redirects to localhost and
        Pikachu captures the auth code automatically.
        """
        # Use provided creds or fall back to stored ones
        cid     = client_id     or self._client_id
        csecret = client_secret or self._client_secret

        if not cid or not csecret:
            raise ValueError(
                "No Google client credentials found.\n"
                "Call authenticate(client_id=..., client_secret=...) once, "
                "or set them via CalendarService.set_credentials()."
            )

        # Store credentials for future runs (Credential Manager, no files)
        self._store_in_keyring(_KEYRING_CLIENT_ID,     cid)
        self._store_in_keyring(_KEYRING_CLIENT_SECRET, csecret)
        self._client_id     = cid
        self._client_secret = csecret

        # Run the local server OAuth flow
        refresh_token = self._run_oauth_flow(cid, csecret)
        if refresh_token:
            self._refresh_token = refresh_token
            self._store_in_keyring(_KEYRING_REFRESH_TOKEN, refresh_token)
            log.info("Google Calendar authenticated. Refresh token stored in Credential Manager.")
        else:
            raise RuntimeError("OAuth2 flow failed — no refresh token received.")

    def set_credentials(self, client_id: str, client_secret: str):
        """
        Store Google app credentials in Windows Credential Manager.
        Call this once (first setup), then never again.
        """
        self._store_in_keyring(_KEYRING_CLIENT_ID,     client_id)
        self._store_in_keyring(_KEYRING_CLIENT_SECRET, client_secret)
        self._client_id     = client_id
        self._client_secret = client_secret
        log.info("Google credentials saved to Windows Credential Manager.")

    def revoke_and_forget(self):
        """
        Revoke the refresh token with Google AND delete it from Credential Manager.
        After this, the app loses all Calendar access and must re-authenticate.
        """
        if self._refresh_token:
            try:
                requests.post(_REVOKE_URL, params={"token": self._refresh_token}, timeout=10)
                log.info("Google refresh token revoked.")
            except Exception as e:
                log.warning("Could not revoke token with Google: %s", e)

        # Delete from Credential Manager
        self._delete_from_keyring(_KEYRING_REFRESH_TOKEN)
        self._refresh_token  = None
        self._access_token   = None
        self._token_expiry   = None
        log.info("All Calendar credentials removed from Credential Manager.")

    # ── Calendar CRUD ─────────────────────────────────────────────────────────

    def list_upcoming(self, days: int = 7) -> List[dict]:
        """
        Return upcoming events for the next *days* days.

        Returns a list of dicts:
            [{"id": "...", "title": "...", "start": "...", "end": "..."}, ...]
        """
        now   = datetime.now(timezone.utc)
        until = now + timedelta(days=days)

        try:
            resp = self._api_get(
                f"{_CALENDAR_BASE}/calendars/primary/events",
                params={
                    "timeMin":      now.isoformat(),
                    "timeMax":      until.isoformat(),
                    "singleEvents": "true",
                    "orderBy":      "startTime",
                    "maxResults":   50,
                },
            )
            items  = resp.get("items", [])
            events = []
            for item in items:
                start = item.get("start", {})
                end   = item.get("end", {})
                events.append({
                    "id":    item.get("id", ""),
                    "title": item.get("summary", "(No title)"),
                    "start": start.get("dateTime", start.get("date", "")),
                    "end":   end.get("dateTime",   end.get("date",   "")),
                    "desc":  item.get("description", ""),
                })
            return events
        except Exception as e:
            log.error("list_upcoming failed: %s", e)
            return []

    def create_event(self, title: str, date: str, start_time: str,
                     end_time: str = None, description: str = "") -> Optional[str]:
        """
        Create a new calendar event.

        Args:
            title:       Event title.
            date:        Date in YYYY-MM-DD format.
            start_time:  Start time in HH:MM (24h).
            end_time:    End time in HH:MM (24h). Defaults to start + 1 hour.
            description: Optional notes.

        Returns:
            The event URL if successful, None on failure.
        """
        if not end_time:
            # Default: 1 hour duration
            h, m   = map(int, start_time.split(":"))
            end_dt = datetime(2000, 1, 1, h, m) + timedelta(hours=1)
            end_time = end_dt.strftime("%H:%M")

        # Build RFC3339 datetimes (assume local timezone)
        tz = self._local_timezone()
        start_dt = f"{date}T{start_time}:00"
        end_dt   = f"{date}T{end_time}:00"

        body = {
            "summary":     title,
            "description": description,
            "start": {"dateTime": start_dt, "timeZone": tz},
            "end":   {"dateTime": end_dt,   "timeZone": tz},
        }
        try:
            resp = self._api_post(
                f"{_CALENDAR_BASE}/calendars/primary/events", body
            )
            url = resp.get("htmlLink", "")
            log.info("Event created: '%s' on %s at %s", title, date, start_time)
            return url
        except Exception as e:
            log.error("create_event failed: %s", e)
            return None

    def delete_event(self, event_id: str) -> bool:
        """Delete an event by its ID."""
        try:
            self._api_delete(
                f"{_CALENDAR_BASE}/calendars/primary/events/{event_id}"
            )
            log.info("Event deleted: %s", event_id)
            return True
        except Exception as e:
            log.error("delete_event failed: %s", e)
            return False

    def reschedule_event(self, event_id: str, new_date: str,
                         new_start_time: str, new_end_time: str = None) -> bool:
        """Reschedule an existing event to a new date/time."""
        try:
            # Fetch existing event
            event = self._api_get(
                f"{_CALENDAR_BASE}/calendars/primary/events/{event_id}"
            )
            tz = self._local_timezone()

            if not new_end_time:
                h, m   = map(int, new_start_time.split(":"))
                end_dt = datetime(2000, 1, 1, h, m) + timedelta(hours=1)
                new_end_time = end_dt.strftime("%H:%M")

            event["start"] = {"dateTime": f"{new_date}T{new_start_time}:00", "timeZone": tz}
            event["end"]   = {"dateTime": f"{new_date}T{new_end_time}:00",   "timeZone": tz}

            self._api_put(
                f"{_CALENDAR_BASE}/calendars/primary/events/{event_id}", event
            )
            log.info("Event rescheduled: %s → %s %s", event_id, new_date, new_start_time)
            return True
        except Exception as e:
            log.error("reschedule_event failed: %s", e)
            return False

    # ── Ollama tool definitions ───────────────────────────────────────────────

    @staticmethod
    def get_tool_definitions() -> list:
        """
        Return Ollama-compatible tool definitions so Mistral can call
        calendar functions via function calling.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "create_calendar_event",
                    "description": "Create a new event in the user's Google Calendar",
                    "parameters": {
                        "type": "object",
                        "required": ["title", "date", "start_time"],
                        "properties": {
                            "title":       {"type": "string",  "description": "Event title/summary"},
                            "date":        {"type": "string",  "description": "Date in YYYY-MM-DD"},
                            "start_time":  {"type": "string",  "description": "Start time HH:MM (24h)"},
                            "end_time":    {"type": "string",  "description": "End time HH:MM (24h), defaults to +1h"},
                            "description": {"type": "string",  "description": "Optional event notes"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_calendar_events",
                    "description": "List the user's upcoming calendar events",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "days": {"type": "integer", "description": "How many days ahead to look (default 7)"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_calendar_event",
                    "description": "Delete a calendar event by its ID",
                    "parameters": {
                        "type": "object",
                        "required": ["event_id"],
                        "properties": {
                            "event_id": {"type": "string", "description": "The event ID to delete"},
                        },
                    },
                },
            },
        ]

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _api_get(self, url: str, params: dict = None) -> dict:
        token = self._get_valid_access_token()
        resp  = requests.get(url, params=params,
                             headers={"Authorization": f"Bearer {token}"}, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _api_post(self, url: str, body: dict) -> dict:
        token = self._get_valid_access_token()
        resp  = requests.post(url, json=body,
                              headers={"Authorization": f"Bearer {token}",
                                       "Content-Type": "application/json"}, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _api_put(self, url: str, body: dict) -> dict:
        token = self._get_valid_access_token()
        resp  = requests.put(url, json=body,
                             headers={"Authorization": f"Bearer {token}",
                                      "Content-Type": "application/json"}, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _api_delete(self, url: str):
        token = self._get_valid_access_token()
        resp  = requests.delete(url,
                                headers={"Authorization": f"Bearer {token}"}, timeout=15)
        resp.raise_for_status()

    # ── Token management ──────────────────────────────────────────────────────

    def _get_valid_access_token(self) -> str:
        """
        Return a valid access token, refreshing silently if expired.
        Access tokens live in memory only (never written to disk).
        """
        with self._lock:
            if self._access_token and self._token_expiry:
                # Give a 60s buffer before actual expiry
                if datetime.now(timezone.utc) < self._token_expiry - timedelta(seconds=60):
                    return self._access_token

            if not self._refresh_token:
                raise RuntimeError("Not authenticated. Call authenticate() first.")

            self._refresh_access_token()
            return self._access_token

    def _refresh_access_token(self):
        """Exchange refresh token for a new access token (in-memory only)."""
        resp = requests.post(_TOKEN_URL, data={
            "client_id":     self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": self._refresh_token,
            "grant_type":    "refresh_token",
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        self._access_token = data["access_token"]
        expires_in         = data.get("expires_in", 3600)
        self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        log.debug("Access token refreshed (expires in %ds)", expires_in)

        # If Google rotated the refresh token (rare), update Credential Manager
        if "refresh_token" in data:
            self._refresh_token = data["refresh_token"]
            self._store_in_keyring(_KEYRING_REFRESH_TOKEN, self._refresh_token)

    def _run_oauth_flow(self, client_id: str, client_secret: str) -> Optional[str]:
        """
        Run the OAuth2 installed-app flow using a temporary local server.
        Opens the user's browser to Google's consent screen.
        Returns the refresh token on success.
        """
        import http.server
        import urllib.parse
        import webbrowser
        import secrets as sec

        port      = 8765
        state     = sec.token_urlsafe(16)
        auth_code = [None]

        # ── Local callback server ──────────────────────────────────────────────
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                if "code" in params:
                    auth_code[0] = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<html><body style='font-family:sans-serif;text-align:center;"
                    b"padding-top:80px;background:#1e1e2e;color:#cdd6f4'>"
                    b"<h2>&#9889; Pikachu is connected to Google Calendar!</h2>"
                    b"<p>You can close this tab now.</p></body></html>"
                )
            def log_message(self, *args):
                pass   # suppress HTTP server logs

        server = http.server.HTTPServer(("127.0.0.1", port), Handler)

        # Build the Google auth URL
        params = urllib.parse.urlencode({
            "client_id":     client_id,
            "redirect_uri":  f"http://127.0.0.1:{port}",
            "response_type": "code",
            "scope":         _SCOPES,
            "state":         state,
            "access_type":   "offline",
            "prompt":        "consent",   # force refresh_token to be returned
        })
        webbrowser.open(f"{_AUTH_URL}?{params}")
        log.info("Browser opened for Google Calendar authorisation.")

        # Wait for the redirect (timeout 120s)
        server.timeout = 120
        server.handle_request()
        server.server_close()

        if not auth_code[0]:
            log.error("OAuth flow timed out or was cancelled.")
            return None

        # Exchange auth code for tokens
        resp = requests.post(_TOKEN_URL, data={
            "client_id":     client_id,
            "client_secret": client_secret,
            "code":          auth_code[0],
            "redirect_uri":  f"http://127.0.0.1:{port}",
            "grant_type":    "authorization_code",
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        self._access_token = data.get("access_token")
        expires_in         = data.get("expires_in", 3600)
        self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        return data.get("refresh_token")

    # ── Keyring helpers (Windows Credential Manager) ──────────────────────────

    @staticmethod
    def _store_in_keyring(key: str, value: str):
        import keyring
        keyring.set_password(_KEYRING_SERVICE, key, value)

    @staticmethod
    def _load_from_keyring_key(key: str) -> Optional[str]:
        import keyring
        return keyring.get_password(_KEYRING_SERVICE, key)

    @staticmethod
    def _delete_from_keyring(key: str):
        import keyring
        try:
            keyring.delete_password(_KEYRING_SERVICE, key)
        except Exception:
            pass

    def _load_from_keyring(self):
        """Load stored credentials from Windows Credential Manager into memory."""
        self._client_id     = self._load_from_keyring_key(_KEYRING_CLIENT_ID)
        self._client_secret = self._load_from_keyring_key(_KEYRING_CLIENT_SECRET)
        self._refresh_token = self._load_from_keyring_key(_KEYRING_REFRESH_TOKEN)
        if self._refresh_token:
            log.debug("Loaded Google Calendar credentials from Credential Manager.")

    # ── Utility ───────────────────────────────────────────────────────────────

    @staticmethod
    def _local_timezone() -> str:
        """Return the local timezone name (e.g. 'Europe/Lisbon')."""
        try:
            import tzlocal
            return str(tzlocal.get_localzone())
        except Exception:
            return "UTC"
