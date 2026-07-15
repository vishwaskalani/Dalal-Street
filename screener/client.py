"""
ScreenerClient — authenticated session for screener.in.

All scrapers import this client and call client.get(url).
Auth is handled once here; nothing else needs to know about it.
"""

import os
import random
import sys
import time
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

BASE_URL = "https://www.screener.in"
LOGIN_URL = f"{BASE_URL}/login/"

_DEFAULT_DELAY     = 1.0   # seconds between every request (avoids triggering rate limits)
_DEFAULT_MAX_RETRY = 5     # max retries on 429 before giving up
_DEFAULT_429_WAIT  = 60    # fallback wait (seconds) when Retry-After header is absent


class AuthError(Exception):
    pass


class ScreenerClient:
    def __init__(
        self,
        env_path: str | None = None,
        request_delay: float = _DEFAULT_DELAY,
        max_retries: int = _DEFAULT_MAX_RETRY,
    ):
        """
        Args:
            env_path:      Path to .env file (default: auto-discover).
            request_delay: Seconds to sleep after every successful GET.
                           Keeps request rate polite. Default 1.0 s.
            max_retries:   How many times to retry a 429 response before
                           propagating the error. Default 5.
        """
        load_dotenv(env_path)

        self._username = os.getenv("SCREENER_USERNAME")
        self._password = os.getenv("SCREENER_PASSWORD")

        if not self._username or not self._password:
            raise AuthError(
                "SCREENER_USERNAME and SCREENER_PASSWORD must be set in your .env file."
            )

        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": BASE_URL,
        })
        self._logged_in    = False
        self._request_delay = request_delay
        self._max_retries   = max_retries

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def login(self) -> None:
        """Authenticate and store session cookies."""
        csrf = self._fetch_csrf()
        resp = self._session.post(
            LOGIN_URL,
            data={
                "username": self._username,
                "password": self._password,
                "csrfmiddlewaretoken": csrf,
            },
            headers={"Referer": LOGIN_URL},
            allow_redirects=True,
        )
        resp.raise_for_status()

        if "sessionid" not in self._session.cookies:
            raise AuthError(
                "Login failed — check SCREENER_USERNAME / SCREENER_PASSWORD in .env"
            )

        self._logged_in = True
        print(f"[screener] Logged in as {self._username}")

    def get(self, url: str) -> requests.Response:
        """
        Authenticated GET with automatic rate-limit handling.

        - Sleeps request_delay seconds after every successful response.
        - On 429, waits (Retry-After header, or 60 s) with exponential
          backoff and retries up to max_retries times before raising.
        """
        if not self._logged_in:
            self.login()

        for attempt in range(self._max_retries + 1):
            resp = self._session.get(url)

            if resp.status_code == 429:
                if attempt == self._max_retries:
                    break  # exhausted — fall through to raise_for_status
                wait = self._backoff_wait(resp, attempt)
                print(
                    f"[screener] 429 rate-limited — waiting {wait}s "
                    f"(retry {attempt + 1}/{self._max_retries})",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue

            resp.raise_for_status()
            # Jitter ±25 % of the configured delay so bursts of requests
            # don't land at perfectly uniform intervals.
            jitter = self._request_delay * random.uniform(-0.25, 0.25)
            time.sleep(max(0.5, self._request_delay + jitter))
            return resp

        # All retries exhausted — raise the 429
        resp.raise_for_status()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _backoff_wait(self, resp: requests.Response, attempt: int) -> float:
        """
        Compute how long to wait after a 429.

        Uses the Retry-After header when present; otherwise falls back to
        _DEFAULT_429_WAIT.  Doubles with each successive attempt.
        """
        try:
            base = float(resp.headers.get("Retry-After", _DEFAULT_429_WAIT))
        except (ValueError, TypeError):
            base = float(_DEFAULT_429_WAIT)
        return base * (2 ** attempt)

    def _fetch_csrf(self) -> str:
        resp = self._session.get(LOGIN_URL)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        token = soup.find("input", {"name": "csrfmiddlewaretoken"})
        if not token:
            raise AuthError("Could not find CSRF token on login page.")
        return token["value"]
