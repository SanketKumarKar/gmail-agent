"""
Gmail Service - Handles Google Gmail API authentication, searching, and message retrieval.
Supports OAuth 2.0 (credentials.json -> token.json) and built-in Demo mode.
"""

import base64
import os
import os.path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Read-only scope for Gmail
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

CREDENTIALS_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
TOKEN_FILE = os.getenv("GMAIL_TOKEN_FILE", "token.json")


def get_demo_emails() -> list[dict[str, Any]]:
    """Return realistic sample emails for testing and demo purposes."""
    return [
        {
            "id": "demo-001",
            "subject": "Offer Letter: Software Engineering Internship - Summer 2026 (Google)",
            "sender": "Google University Programs <recruiting-noreply@google.com>",
            "date": "Wed, 02 Sep 2026 10:15:00 +0000",
            "snippet": "Congratulations! We are thrilled to offer you a position as Software Engineering Intern...",
            "body": (
                "Dear Sanket,\n\n"
                "We are thrilled to extend an offer for the Software Engineering Intern position "
                "at Google for Summer 2026. Your stipend will be ₹1,10,000 per month, plus accommodation support.\n\n"
                "Company: Google India Pvt Ltd\n"
                "Role: Software Engineering Intern (Summer 2026)\n"
                "Location: Bangalore, India / Hybrid\n"
                "Stipend: ₹1,10,000/month\n"
                "Joining Date: May 18, 2026\n\n"
                "Action Required: Please review and sign the attached offer letter and acceptance form "
                "before September 10, 2026, 11:59 PM IST.\n\n"
                "Best regards,\nGoogle Student Recruitment Team"
            ),
        },
        {
            "id": "demo-002",
            "subject": "Interview Invitation: Microsoft Campus Recruitment 2026 - Final Technical Round",
            "sender": "Microsoft Careers <campus-recruitment@microsoft.com>",
            "date": "Tue, 01 Sep 2026 15:40:00 +0000",
            "snippet": "You have been shortlisted for the final technical interview round for the SDE-1 role...",
            "body": (
                "Hi Sanket,\n\n"
                "Congratulations on clearing the online coding assessment! You have been selected for the "
                "Final Technical & System Design interview round for the full-time Software Development Engineer (SDE-1) position.\n\n"
                "Company: Microsoft Corporation India\n"
                "Role: Software Development Engineer - Full Time\n"
                "Package/CTC: 44 LPA (Base + Stocks + Joining Bonus)\n"
                "Interview Date & Time: September 5, 2026 at 2:00 PM IST\n"
                "Platform: Microsoft Teams (Link enclosed)\n\n"
                "Action Required: Confirm your availability by replying to this email or clicking the calendar invite by tomorrow 5:00 PM.\n\n"
                "Warm regards,\nMicrosoft University Talent Acquisition"
            ),
        },
        {
            "id": "demo-003",
            "subject": "Important: Campus Placement Drive - Amazon SDE Internship Shortlist & Schedule",
            "sender": "Training & Placement Cell <placement-cell@university.edu>",
            "date": "Mon, 31 Aug 2026 09:30:00 +0000",
            "snippet": "Dear Students, please find the list of shortlisted candidates for Amazon Internship Drive...",
            "body": (
                "Dear Students,\n\n"
                "The Training and Placement Cell is pleased to announce that Amazon will be conducting its on-campus "
                "recruitment drive for 6-Month Internships (Jan - June 2027) on September 8, 2026.\n\n"
                "Eligible Branches: CSE / IT / ECE\n"
                "Package/Stipend: ₹80,000/month with PPO opportunity\n"
                "Registration Deadline: September 4, 2026 at 6:00 PM IST\n"
                "Resume Shortlisting & PPT: September 7, 2026\n\n"
                "Action Required: Eligible candidates must register on the T&P portal and upload their updated resumes.\n\n"
                "Regards,\nHead, Placement & Internship Committee"
            ),
        },
        {
            "id": "demo-004",
            "subject": "Your weekly newsletter from Tech Weekly Digest",
            "sender": "Tech Digest <news@techdigest.io>",
            "date": "Sun, 30 Aug 2026 08:00:00 +0000",
            "snippet": "Here are top 10 trends in AI, Web3, and cloud infrastructure this week...",
            "body": "Top 10 trends in tech this week: Large language models, multi-agent frameworks, quantum computing.",
        },
    ]


class GmailService:
    """Manages Gmail authentication and API interactions."""

    def __init__(self, credentials_path: str = CREDENTIALS_FILE, token_path: str = TOKEN_FILE):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self._service = None

    def authenticate(self, interactive: bool = True) -> bool:
        """
        Authenticate with Gmail using OAuth 2.0.
        Loads from token.json or launches local server flow if interactive.
        """
        creds = None
        if os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            except Exception as e:
                print(f"Warning: Could not load token file: {e}")

        # If there are no valid credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"Could not refresh token: {e}")
                    creds = None

            if not creds and interactive:
                if not os.path.exists(self.credentials_path):
                    print(
                        f"❌ Gmail OAuth credentials file not found: '{self.credentials_path}'.\n"
                        f"To enable live Gmail access:\n"
                        f"1. Go to Google Cloud Console (https://console.cloud.google.com/)\n"
                        f"2. Enable the Gmail API.\n"
                        f"3. Create OAuth 2.0 Client ID (Application type: Desktop app).\n"
                        f"4. Download client secret JSON and save it as '{self.credentials_path}'.\n"
                    )
                    return False

                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)

            if creds:
                # Save credentials for next run
                with open(self.token_path, "w") as token_file:
                    token_file.write(creds.to_json())

        if creds and creds.valid:
            self._service = build("gmail", "v1", credentials=creds)
            return True

        return False

    def is_authenticated(self) -> bool:
        """Check if service is initialized and authenticated."""
        return self._service is not None

    def search_emails(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        """
        Search for messages in Gmail matching the query.
        Returns a list of parsed email dictionaries.
        """
        if not self._service:
            if not self.authenticate(interactive=False):
                raise RuntimeError(
                    "Gmail service not authenticated. Run with '--auth' or configure credentials.json."
                )

        results = (
            self._service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )

        messages = results.get("messages", [])
        emails = []

        for msg in messages:
            msg_id = msg["id"]
            email_detail = self.get_message_details(msg_id)
            if email_detail:
                emails.append(email_detail)

        return emails

    def get_message_details(self, message_id: str) -> dict[str, Any] | None:
        """Retrieve and parse a single Gmail message by ID."""
        if not self._service:
            return None

        try:
            msg = (
                self._service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )

            headers = msg.get("payload", {}).get("headers", [])
            header_dict = {h["name"].lower(): h["value"] for h in headers}

            subject = header_dict.get("subject", "No Subject")
            sender = header_dict.get("from", "Unknown")
            date = header_dict.get("date", "")
            snippet = msg.get("snippet", "")

            # Extract body
            body = self._extract_body(msg.get("payload", {})) or snippet

            return {
                "id": message_id,
                "subject": subject,
                "sender": sender,
                "date": date,
                "snippet": snippet,
                "body": body,
            }
        except Exception as e:
            print(f"Error fetching message {message_id}: {e}")
            return None

    def _extract_body(self, payload: dict) -> str:
        """Recursively extract plain text body from message payload."""
        if not payload:
            return ""

        mime_type = payload.get("mimeType", "")
        parts = payload.get("parts", [])
        body_data = payload.get("body", {}).get("data", "")

        if mime_type == "text/plain" and body_data:
            try:
                return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
            except Exception:
                return ""

        for part in parts:
            if part.get("mimeType") == "text/plain":
                part_data = part.get("body", {}).get("data", "")
                if part_data:
                    try:
                        return base64.urlsafe_b64decode(part_data).decode(
                            "utf-8", errors="replace"
                        )
                    except Exception:
                        pass

        # Fallback to text/html if text/plain not found
        for part in parts:
            if part.get("mimeType") == "text/html":
                part_data = part.get("body", {}).get("data", "")
                if part_data:
                    try:
                        decoded = base64.urlsafe_b64decode(part_data).decode(
                            "utf-8", errors="replace"
                        )
                        # Basic tag stripping
                        import re
                        return re.sub(r"<[^>]+>", " ", decoded)
                    except Exception:
                        pass

        return ""
