"""Release-blocking evals and measurements (EPIC-12).

Implements: US-12.1 (``redaction_recall``), US-12.2 (``classification``, ``draft_acceptance``),
US-12.3 (``latency``), US-12.4 (``egress_check``); ``python -m claimcoach.evals`` runs each one for
the Makefile and writes its typed JSON report to ``evidence/US-12.x/``. Rules: ES-5, NFR-1 to NFR-5.

Every eval runs against the running worker on loopback, through the same REST routes the pane
uses, and never imports model code: the worker owns the models (PC-4, BR-12).
"""
