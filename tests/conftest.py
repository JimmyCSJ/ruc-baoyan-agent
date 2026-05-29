"""Pytest defaults: disable API auth gate so existing tests stay unchanged."""

import os

os.environ["AUTH_REQUIRED"] = "false"
