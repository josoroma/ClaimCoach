"""Local model management: the role registry, server lifecycle, memory guard, and acquisition.

Implements: EPIC-2 (US-2.1 to US-2.4). Rules: BR-1, BR-11, BR-12.

Submodules are imported explicitly. The gateway imports only ``claimcoach.models.types``, which
needs neither YAML nor process management (PC-4).
"""
