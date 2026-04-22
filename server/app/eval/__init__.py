"""BFCL-style tool-selection eval gate for the hybrid preamble (task #7).

Measures how reliably the local model picks the right MCP tool (or refrains
from calling one) given a short user utterance. Runs against the live vLLM
engine via a dedicated HTTP endpoint; the CLI orchestrator scores the
responses and emits a markdown report.

The 85% pass-rate gate determines whether task #7's hybrid tool-use
preamble ships with real tools wired in or falls back to the JSON-only
single-pass path until prompts improve.
"""
