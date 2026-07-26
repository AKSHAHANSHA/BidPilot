"""AI pipeline: provider adapters, strict structured models, prompts, and extraction.

The LLM extracts and explains; application code validates and decides
(`docs/03_AI_PIPELINE_AND_SCORING.md` §1). Provider SDK calls live only in `providers/`;
everything else operates on validated Pydantic records.
"""
