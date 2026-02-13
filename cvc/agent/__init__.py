"""
cvc.agent — The CVC Agentic Coding Assistant.

A Claude Code-style interactive coding agent that runs in your terminal,
powered by CVC's Time Machine technology. Supports multiple LLM providers
(Anthropic, OpenAI, Google, Ollama) and provides:

    - File reading, writing, editing
    - Shell command execution (cross-platform)
    - Codebase search (glob, grep)
    - CVC Time Machine operations (commit, branch, merge, restore, search)
    - Auto-commit at configurable intervals
    - Slash commands for quick operations
    - Streaming responses with Rich rendering

Usage:
    cvc agent                   # Start the interactive agent
    cvc agent --provider openai # Use a specific provider
    cvc agent --model gpt-5.2  # Use a specific model

The agent has full access to CVC's cognitive version control system,
enabling time-travel through conversation history, branching for
exploration, and semantic merging of insights.
"""

__all__ = ["run_agent"]

from cvc.agent.chat import run_agent
