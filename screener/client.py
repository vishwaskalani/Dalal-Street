"""
ScreenerClient — authenticated session for screener.in.

All scrapers import this client and call client.get(url).
Auth is handled once here; nothing else needs to know about it.
"""

import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

BASE_URL = "https://www.screener.in"
LOGIN_URL = f"{BASE_URL}/login/"


class AuthError(Exception):
    pass


class ScreenerClient:
    def __init__(self, env_path: str | None = None):
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
        self._logged_in = False

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

        # screener.in sets a sessionid cookie on successful login
        if "sessionid" not in self._session.cookies:
            raise AuthError(
                "Login failed — check SCREENER_USERNAME / SCREENER_PASSWORD in .env"
            )

        self._logged_in = True
        print(f"[screener] Logged in as {self._username}")

    def get(self, url: str) -> requests.Response:
        """Authenticated GET. Logs in automatically on first call."""
        if not self._logged_in:
            self.login()

        resp = self._session.get(url)
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_csrf(self) -> str:
        resp = self._session.get(LOGIN_URL)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        token = soup.find("input", {"name": "csrfmiddlewaretoken"})
        if not token:
            raise AuthError("Could not find CSRF token on login page.")
        return token["value"]
