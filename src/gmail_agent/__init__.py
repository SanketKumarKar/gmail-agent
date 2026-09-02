"""Gmail Agent package for summarizing internship/placement emails."""

from .agent import create_gmail_agent, run_agent, AgentState

__all__ = ["create_gmail_agent", "run_agent", "AgentState"]