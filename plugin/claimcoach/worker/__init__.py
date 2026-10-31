"""The ClaimCoach worker: an app-owned process that runs heavy work outside the gateway.

Implements: US-1.2 and the PRD §7.9 worker decision (ADR-0001). Rules: PC-4, PC-5, PC-6, BR-11.

Submodules are imported explicitly; this package imports nothing so the gateway can use
``claimcoach.worker.config`` without pulling in uvicorn.
"""
