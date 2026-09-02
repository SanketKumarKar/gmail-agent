"""
Gmail Agent - Summarizes unread internship and placement related emails using LangGraph and Gmail API.
Supports real-time token streaming and clean text rendering without signatures or metadata.
"""

import asyncio
import logging
import os
import re
import warnings
from typing import Any, AsyncGenerator, TypedDict
from dotenv import load_dotenv

# Suppress all library warnings and logging noise
warnings.filterwarnings("ignore")
warnings.simplefilter("ignore")
os.environ["PYTHONWARNINGS"] = "ignore"
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GLOG_minloglevel"] = "2"

logging.getLogger("google").setLevel(logging.ERROR)
logging.getLogger("google.genai").setLevel(logging.ERROR)
logging.getLogger("google_genai").setLevel(logging.ERROR)
logging.getLogger("langchain_google_genai").setLevel(logging.ERROR)

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

from .gmail_service import GmailService, get_demo_emails

# Load environment variables
load_dotenv()


class AgentState(TypedDict):
    """State for the Gmail Agent"""
    emails: list[dict[str, Any]]
    summaries: list[str]
    relevant_emails: list[dict[str, Any]]
    query: str
    demo: bool
    unread_only: bool
    max_results: int
    error: str | None


# ── LLM factory ─────────────────────────────────────────────────────────────

def create_llm() -> BaseChatModel | None:
    """Initialize the language model from environment variables."""
    openai_key = os.getenv("OPENAI_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

    if openai_key:
        return ChatOpenAI(model="gpt-4o", temperature=0.3, api_key=openai_key)
    elif google_key:
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0.3,
            google_api_key=google_key,
        )
    return None


def _extract_text_chunk(content: Any) -> str:
    """Extract only clean human-readable text for streaming and summarization (ignores all signatures & extras)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                val = item.get("text")
                if isinstance(val, str) and val:
                    parts.append(val)
            elif hasattr(item, "text"):
                val = getattr(item, "text", "")
                if isinstance(val, str) and val:
                    parts.append(val)
        return "".join(parts)
    if isinstance(content, dict) and "text" in content:
        val = content.get("text")
        return val if isinstance(val, str) else ""
    return ""


def build_summary_prompt(email: dict[str, Any]) -> str:
    """Construct structured extraction prompt for placement/internship emails."""
    subject = email.get("subject", "No Subject")
    sender = email.get("sender", "Unknown")
    date = email.get("date", "")
    body = email.get("body", email.get("snippet", ""))

    return (
        "You are an assistant tracking internship & placement emails for a college student.\n"
        "Analyze and summarize this email concisely with clear bullet points:\n\n"
        "* 🏢 **Company / Organization:** [Name]\n"
        "* 🎯 **Role / Program / Event:** [Title]\n"
        "* 💰 **CTC / Stipend / Location:** [Details or 'Not mentioned']\n"
        "* ⏳ **Action Required & Deadline:** [Next steps and due date/time]\n\n"
        "Output ONLY the bullet points above. Do not include signatures, raw code blocks, or irrelevant email footers.\n\n"
        f"Email Subject: {subject}\n"
        f"From: {sender}\n"
        f"Date: {date}\n\n"
        f"Content:\n{body[:3500]}"
    )


# ── Node helpers ─────────────────────────────────────────────────────────────

INTERNSHIP_KEYWORDS = [
    "internship", "intern", "placement", "offer letter", "selected",
    "interview", "hiring", "recruitment", "package", "ctc", "stipend",
    "joining", "placement drive", "campus recruitment", "job opportunity",
    "offer accepted", "onboarding", "shortlist", "assessment", "hackathon",
    "workshop", "registration",
]

DEFAULT_UNREAD_QUERY = (
    "is:unread (internship OR intern OR placement OR interview OR hiring OR recruitment "
    "OR \"offer letter\" OR \"campus drive\" OR shortlist OR assessment)"
)

DEFAULT_ALL_QUERY = (
    "internship OR intern OR placement OR interview OR hiring OR recruitment "
    "OR \"offer letter\" OR \"campus drive\" OR shortlist OR assessment"
)


def _make_fetch_node():
    """Return a fetch_emails graph node."""

    def fetch_emails_node(state: AgentState) -> AgentState:
        unread_only = state.get("unread_only", True)
        is_demo = state.get("demo", False)
        max_results = state.get("max_results", 20)

        user_query = state.get("query")
        if user_query:
            if unread_only and "is:unread" not in user_query and "is:read" not in user_query:
                query = f"is:unread ({user_query})"
            else:
                query = user_query
        else:
            query = DEFAULT_UNREAD_QUERY if unread_only else DEFAULT_ALL_QUERY

        state["query"] = query

        if state.get("emails"):
            return state

        if is_demo:
            state["emails"] = get_demo_emails()
            state["error"] = None
            return state

        gmail_service = GmailService()
        if not gmail_service.authenticate(interactive=False):
            if not os.path.exists(gmail_service.credentials_path) and not os.path.exists(gmail_service.token_path):
                print("ℹ️ No Gmail credentials found. Falling back to Demo Mode.")
                state["emails"] = get_demo_emails()
                state["demo"] = True
                state["error"] = None
                return state
            else:
                state["emails"] = []
                state["error"] = "Gmail authentication failed. Run 'python main.py --auth' to log in."
                return state

        try:
            emails = gmail_service.search_emails(query=query, max_results=max_results)
            state["emails"] = emails
            state["error"] = None
        except Exception as exc:
            state["emails"] = []
            state["error"] = f"Failed to fetch emails from Gmail: {exc}"

        return state

    return fetch_emails_node


def _make_filter_node():
    """Return a filter_relevant graph node."""

    def filter_relevant_emails_node(state: AgentState) -> AgentState:
        emails = state.get("emails", [])
        relevant = []

        for email in emails:
            subject = email.get("subject", "").lower()
            snippet = email.get("snippet", "").lower()
            body = email.get("body", "").lower()

            matched = any(
                kw in subject or kw in snippet or kw in body
                for kw in INTERNSHIP_KEYWORDS
            )
            if matched:
                relevant.append(email)

        state["relevant_emails"] = relevant
        return state

    return filter_relevant_emails_node


def _make_summarize_node(llm: BaseChatModel | None):
    """Return an async summarize graph node that extracts clear structured bullet points."""
    sem = asyncio.Semaphore(3)

    async def summarize_single_email(email: dict[str, Any]) -> str:
        subject = email.get("subject", "No Subject")
        snippet = email.get("snippet", "")
        body = email.get("body", snippet)
        sender = email.get("sender", "Unknown")
        date = email.get("date", "")

        if llm is not None:
            prompt = build_summary_prompt(email)
            ai_summary = ""
            for attempt in range(3):
                async with sem:
                    try:
                        response = await llm.ainvoke([HumanMessage(content=prompt)])
                        ai_summary = _extract_text_chunk(response.content).strip()
                        break
                    except Exception as exc:
                        err_str = str(exc)
                        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                            await asyncio.sleep(2 * (attempt + 1))
                            continue
                        ai_summary = f"📌 **Snippet**: {snippet[:200]}"
                        break
            if not ai_summary:
                ai_summary = f"📌 **Snippet**: {snippet or body[:250]}..."
        else:
            ai_summary = (
                f"📌 **Snippet**: {snippet or body[:250]}...\n"
                f"*(Add GOOGLE_API_KEY or OPENAI_API_KEY in .env for full AI summary)*"
            )

        return (
            f"📧 **{subject}**\n"
            f"   _From: {sender} | Date: {date}_\n\n"
            f"{ai_summary}"
        )

    async def summarize_emails_node(state: AgentState) -> AgentState:
        relevant_emails = state.get("relevant_emails", [])

        if not relevant_emails:
            state["summaries"] = ["No unread internship/placement emails found."]
            return state

        tasks = [summarize_single_email(email) for email in relevant_emails]
        summaries = await asyncio.gather(*tasks)
        state["summaries"] = list(summaries)
        return state

    return summarize_emails_node


# ── Graph builder ────────────────────────────────────────────────────────────

def create_gmail_agent():
    """Build and compile the LangGraph agent."""
    llm = create_llm()

    workflow = StateGraph(AgentState)
    workflow.add_node("fetch_emails", _make_fetch_node())
    workflow.add_node("filter_relevant", _make_filter_node())
    workflow.add_node("summarize", _make_summarize_node(llm))

    workflow.set_entry_point("fetch_emails")
    workflow.add_edge("fetch_emails", "filter_relevant")
    workflow.add_edge("filter_relevant", "summarize")
    workflow.add_edge("summarize", END)

    return workflow.compile()


# ── Public API ───────────────────────────────────────────────────────────────

async def run_agent(
    query: str | None = None,
    emails: list[dict[str, Any]] | None = None,
    demo: bool = False,
    unread_only: bool = True,
    max_results: int = 20,
) -> dict[str, Any]:
    """Run the Gmail agent in batch mode."""
    agent = create_gmail_agent()

    initial_state: AgentState = {
        "emails": emails or [],
        "summaries": [],
        "relevant_emails": [],
        "query": query or "",
        "demo": demo,
        "unread_only": unread_only,
        "max_results": max_results,
        "error": None,
    }

    try:
        result = await agent.ainvoke(initial_state)
        return {
            "summaries": result.get("summaries", []),
            "count": len(result.get("relevant_emails", [])),
            "demo": result.get("demo", False),
            "query": result.get("query", ""),
            "error": result.get("error"),
        }
    except Exception as exc:
        return {"summaries": [], "count": 0, "demo": demo, "error": str(exc)}


async def stream_agent(
    query: str | None = None,
    demo: bool = False,
    unread_only: bool = True,
    max_results: int = 20,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Stream Gmail agent results in real-time.
    Yields clean events without signatures or metadata.
    """
    fetch_node = _make_fetch_node()
    state: AgentState = {
        "emails": [],
        "summaries": [],
        "relevant_emails": [],
        "query": query or "",
        "demo": demo,
        "unread_only": unread_only,
        "max_results": max_results,
        "error": None,
    }

    state = fetch_node(state)
    if state.get("error"):
        yield {"type": "error", "error": state["error"]}
        return

    filter_node = _make_filter_node()
    state = filter_node(state)

    relevant = state.get("relevant_emails", [])
    total = len(relevant)
    yield {"type": "found", "count": total, "is_demo": state.get("demo", False)}

    if total == 0:
        yield {"type": "complete", "total": 0}
        return

    llm = create_llm()

    for idx, email in enumerate(relevant, 1):
        yield {"type": "email_header", "index": idx, "total": total, "email": email}

        snippet = email.get("snippet", "")
        body = email.get("body", snippet)

        full_summary_tokens = []

        if llm is not None:
            prompt = build_summary_prompt(email)
            try:
                async for chunk in llm.astream([HumanMessage(content=prompt)]):
                    token_text = _extract_text_chunk(chunk.content)
                    if token_text:
                        full_summary_tokens.append(token_text)
                        yield {"type": "token", "index": idx, "token": token_text}
            except Exception as exc:
                fallback = f"📌 **Snippet**: {snippet or body[:250]}..."
                yield {"type": "token", "index": idx, "token": fallback}
                full_summary_tokens = [fallback]
        else:
            fallback = (
                f"📌 **Snippet**: {snippet or body[:250]}...\n"
                f"*(Add GOOGLE_API_KEY or OPENAI_API_KEY in .env for full AI summary)*"
            )
            yield {"type": "token", "index": idx, "token": fallback}
            full_summary_tokens = [fallback]

        full_summary = "".join(full_summary_tokens).strip()
        yield {"type": "email_done", "index": idx, "summary": full_summary}

    yield {"type": "complete", "total": total}
