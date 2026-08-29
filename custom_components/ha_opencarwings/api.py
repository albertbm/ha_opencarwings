"""Async client for OpenCARWINGS API (JWT auth).

Provides methods to obtain and refresh JWT tokens and make authenticated requests.
"""
from __future__ import annotations

DEFAULT_API_BASE = "https://opencarwings.viaaq.eu"

class AuthenticationError(Exception):
    pass

import opencarwings_client

def get_client(base_url: str = DEFAULT_API_BASE, api_token: str | None=None) -> opencarwings_client.ApiClient:
    configuration = opencarwings_client.Configuration(
        host=base_url
    )

    if api_token is not None and len(api_token) > 0:
        configuration.api_key_prefix['Personal API Key'] = 'Token'
        configuration.api_key['Personal API Key'] = api_token
    client = opencarwings_client.ApiClient(configuration)
    client.set_default_header("User-Agent", "OpenCARWINGS-HomeAssistant/1.0")
    return client
