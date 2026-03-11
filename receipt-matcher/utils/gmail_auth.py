"""
Gmail OAuth2 authentication helper.

Manages per-account token files so multiple Gmail accounts can be
authorised independently.  The first run for each account opens a
browser-based consent flow; subsequent runs reuse the cached token.
"""

import json
import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import config

logger = logging.getLogger(__name__)


def _client_config() -> dict:
    """Build the OAuth client-config dict from environment variables."""
    return {
        "installed": {
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "redirect_uris": ["http://localhost", "urn:ietf:wg:oauth:2.0:oob"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def _token_path(email: str) -> Path:
    """Return the token file path for a given Gmail account."""
    safe = email.replace("@", "_at_").replace(".", "_")
    return config.TOKEN_DIR / f"token_{safe}.json"


def get_gmail_service(email: str):
    """
    Return an authenticated Gmail API service for *email*.

    If no valid cached token exists the user is prompted to authorise
    via the standard OAuth2 browser flow.
    """
    token_file = _token_path(email)
    creds: Credentials | None = None

    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), config.GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing token for %s", email)
            creds.refresh(Request())
        else:
            logger.info("Starting OAuth2 flow for %s – a browser window will open.", email)
            flow = InstalledAppFlow.from_client_config(
                _client_config(), config.GMAIL_SCOPES
            )
            # hint=email pre-fills the account picker in the consent screen
            creds = flow.run_local_server(port=0, login_hint=email)

        token_file.write_text(creds.to_json())
        logger.info("Token saved to %s", token_file)

    return build("gmail", "v1", credentials=creds)
