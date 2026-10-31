"""ClaimCoach app package: the code shared by the agent half, the backend half, and the worker.

Implements: US-1.1 (package scaffold). Rules: BR-13 (state lives outside the install dir), PC-2.
"""

from typing import Final

__all__ = ["PLUGIN_NAME", "__version__"]

PLUGIN_NAME: Final = "claimcoach"
"""Hermes plugin id; also the plugin data dir name and the REST namespace."""

__version__: Final = "0.1.0"
