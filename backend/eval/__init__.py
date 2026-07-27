"""Gold-set evaluation for the BidPilot analysis pipeline.

This package holds the fictional gold dataset (`gold/`) and the harness that runs the *real*
domain logic — requirement extraction, citation verification, deterministic evidence matching,
and deterministic scoring — against it. It never touches the database or the job runner; those
have their own integration tests. See `scripts/evaluate_pipeline.py` for the CLI.
"""
