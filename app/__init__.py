"""
Marrow — Application Package

Core modules for the Marrow FinOps × SecOps intelligence platform.

Modules:
    config      – Environment variables, paths, and tunable constants.
    correlator  – Deterministic join of billing + security data by resource_id.
    reasoner    – LLM-powered decision engine (Fireworks AI / deterministic fallback).
    models      – SQLite persistence layer for scan history and recommendations.
    routes      – Flask blueprint exposing the REST API and dashboard views.
    report      – PDF report generation for stakeholder handoff.
    cli         – Command-line interface for standalone correlation runs.
"""
