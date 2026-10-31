"""ClaimCoach's own corpus: a global scope (no PHI) and a per-profile user scope (PHI).

Implements: EPIC-4 (US-4.1 to US-4.6). Rules: BR-5, BR-6, BR-7, BR-13, PRD §9.

The gateway may import only ``types``, ``bundle``, and ``paths`` (pure Pydantic and path logic);
everything that touches SQLite, numpy, the Keychain, or a model runs in the worker (PC-4).
"""
