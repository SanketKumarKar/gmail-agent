"""
Gmail MCP Client - Connects to Google MCP Server for Gmail access.
"""

import asyncio
from typing import AsyncIterator
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class GmailMCPClient:
    """Client for connecting to Gmail via MCP server."""

    def __init__(self, server_command: str | None = None):
        """
        Initialize the Gmail MCP client.

        Args:
            server_command: Command to start the MCP server.
                          Defaults to npx for @modelcontextprotocol/server-gmail
        """
        self.server_command = server_command or "npx"
        self.session: ClientSession | None = None

    async def connect(self):
        """Establish connection to the MCP server."""
        server_params = StdioServerParameters(
            command=self.server_command,
            args=["-y", "@modelcontextprotocol/server-gmail"],
            env={"NODE_ENV": "development"}
        )

        async with stdio_client(server_params) as (read, write):
            self.session = ClientSession(read, write)
            await self.session.initialize()

            # List available tools
            tools = await self.session.list_tools()
            print(f"Connected to Gmail MCP server. Available tools: {len(tools.tools)}")

    async def search_emails(
        self,
        query: str,
        max_results: int = 50
    ) -> list[dict]:
        """
        Search for emails matching the query.

        Args:
            query: Gmail search query
            max_results: Maximum number of results

        Returns:
            List of email dictionaries
        """
        if not self.session:
            await self.connect()

        result = await self.session.call_tool(
            "gmail_search_messages",
            arguments={
                "query": query,
                "maxResults": max_results
            }
        )

        # Parse the result
        emails = []
        if result.content:
            for item in result.content:
                if hasattr(item, "text"):
                    import json
                    try:
                        email_data = json.loads(item.text)
                        emails.append(email_data)
                    except json.JSONDecodeError:
                        pass

        return emails

    async def get_email_details(self, message_id: str) -> dict:
        """
        Get full details of a specific email.

        Args:
            message_id: The Gmail message ID

        Returns:
            Email details dictionary
        """
        if not self.session:
            await self.connect()

        result = await self.session.call_tool(
            "gmail_get_message",
            arguments={"messageId": message_id}
        )

        if result.content and hasattr(result.content[0], "text"):
            import json
            return json.loads(result.content[0].text)

        return {}

    async def close(self):
        """Close the MCP connection."""
        if self.session:
            await self.session.close()
            self.session = None


async def get_gmail_client() -> GmailMCPClient:
    """Factory function to get a configured Gmail MCP client."""
    client = GmailMCPClient()
    await client.connect()
    return client