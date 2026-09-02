import sys
import asyncio
import argparse
import json
import logging
import os
import warnings
from datetime import datetime

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

# Ensure UTF-8 output encoding for emojis on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass


from .agent import run_agent, stream_agent
from .gmail_service import GmailService


async def main(
    query: str | None = None,
    output_format: str = "text",
    demo: bool = False,
    unread_only: bool = True,
    max_results: int = 20,
):
    """
    Run the Gmail agent with real-time token streaming.
    """
    mode_str = " (DEMO MODE)" if demo else ""
    scope_str = "Unread" if unread_only else "All"

    if output_format == "json":
        result = await run_agent(
            query=query,
            demo=demo,
            unread_only=unread_only,
            max_results=max_results,
        )
        print(json.dumps(result, indent=2))
        return

    print("=" * 70)
    print(f"📧 Gmail Agent - {scope_str} Internship & Placement Summarizer{mode_str}")
    print("=" * 70)
    print()

    total_count = 0
    is_demo_run = demo

    # Stream the agent in real time
    async for event in stream_agent(
        query=query,
        demo=demo,
        unread_only=unread_only,
        max_results=max_results,
    ):
        event_type = event.get("type")

        if event_type == "error":
            print(f"❌ Error: {event['error']}")
            return

        elif event_type == "found":
            count = event["count"]
            total_count = count
            is_demo_run = event.get("is_demo", False)
            source_label = "sample demo emails" if is_demo_run else "Gmail inbox"
            print(f"📬 Found {count} relevant {scope_str.lower()} emails in {source_label}\n")

            if count == 0:
                print("No matching internship/placement emails found.")
                return

            print("=" * 70)
            print("📋 EMAIL SUMMARIES (STREAMING LIVE)")
            print("=" * 70)
            print()

        elif event_type == "email_header":
            idx = event["index"]
            total = event["total"]
            email = event["email"]
            subject = email.get("subject", "No Subject")
            sender = email.get("sender", "Unknown")
            date = email.get("date", "")

            print(f"[{idx}/{total}] 📧 **{subject}**")
            print(f"      _From: {sender} | Date: {date}_")
            print()

        elif event_type == "token":
            # Stream token live to console
            sys.stdout.write(event["token"])
            sys.stdout.flush()

        elif event_type == "email_done":
            print()
            print("-" * 70)
            print()

        elif event_type == "complete":
            print(f"✅ Total: {event['total']} emails summarized")
            if is_demo_run:
                print("💡 Tip: To connect to your real Gmail, run 'python main.py --auth'")
            print(f"🕐 Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def setup_auth():
    """Authenticate Gmail account via browser OAuth flow."""
    print("\n🔐 Gmail OAuth 2.0 Setup")
    print("=" * 50)
    service = GmailService()

    if not os.path.exists(service.credentials_path):
        print(f"❌ '{service.credentials_path}' not found in current directory.")
        print("\nSetup Instructions:")
        print("1. Go to Google Cloud Console: https://console.cloud.google.com/")
        print("2. Create a project and enable the 'Gmail API'.")
        print("3. Go to 'APIs & Services' > 'Credentials' > 'Create Credentials' > 'OAuth Client ID'.")
        print("4. Select Application type: 'Desktop App'.")
        print("5. Download the JSON file and save it as 'credentials.json' in this directory.")
        print("6. Run 'python main.py --auth' again to log in via browser.")
        return

    print("Opening browser for Google OAuth sign-in...")
    success = service.authenticate(interactive=True)
    if success:
        print("\n🎉 Authentication successful! 'token.json' has been created.")
        print("You can now run 'python main.py' to summarize your live Gmail emails.")
    else:
        print("\n❌ Authentication failed.")


def cli():
    """Command-line interface for Gmail Agent."""
    parser = argparse.ArgumentParser(
        description="Gmail Agent - Summarize unread internship and placement emails"
    )
    parser.add_argument(
        "-q", "--query",
        type=str,
        help="Custom search query for emails (e.g. 'internship offer')",
        default=None
    )
    parser.add_argument(
        "-f", "--format",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (text or json)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Search all emails (both read and unread). By default, only unread emails are processed."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run using realistic sample internship/placement emails without needing Gmail credentials"
    )
    parser.add_argument(
        "-m", "--max",
        type=int,
        default=10,
        help="Maximum number of emails to fetch from Gmail (default: 10)"
    )
    parser.add_argument(
        "--auth",
        action="store_true",
        help="Run interactive Gmail OAuth2 authentication"
    )

    args = parser.parse_args()

    if args.auth:
        setup_auth()
    else:
        unread_only = not args.all
        asyncio.run(
            main(
                query=args.query,
                output_format=args.format,
                demo=args.demo,
                unread_only=unread_only,
                max_results=args.max,
            )
        )


if __name__ == "__main__":
    cli()
