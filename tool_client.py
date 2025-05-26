import asyncio
from contextlib import AsyncExitStack

import nest_asyncio
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Apply nest_asyncio to allow nested event loops (needed for Jupyter/IPython)
nest_asyncio.apply()

# Load environment variables
load_dotenv()


class MCPClient:
    def __init__(self):
        """Initialize client."""
        # Initialize session and client objects
        self.session: ClientSession | None = None
        self.exit_stack = AsyncExitStack()
        self.stdio: object | None = None
        self.write: object | None = None

    async def connect_to_server(
        self, server_script_path: str = "server.py", server_script_args: list[str] | str = []
    ):
        """Connect to an MCP server.

        Args:
            server_script_path: Path to the server script.
            server_script_args: Arguments passed to the script, if any.
        """
        # Server configuration
        server_script_args = [server_script_args] if type(server_script_args) is str else server_script_args
        server_params = StdioServerParameters(
            command="python",
            args=[server_script_path] + server_script_args,
        )

        # Connect to the server
        stdio_transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(self.stdio, self.write)
        )

        # Initialize the connection
        await self.session.initialize()

        # List available tools
        tools_result = await self.session.list_tools()
        print("Connected to server with tools:")
        for tool in tools_result.tools:
            print(f"  - {tool.name}: {tool.description}")

    async def get_mcp_tools(self) -> list[dict[str, object]]:
        """Get available tools from the MCP server in OpenAI format.

        Returns:
            A list of tools in OpenAI format.
        """
        tools_result = await self.session.list_tools()
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                },
            }
            for tool in tools_result.tools
        ]

    async def run_tool(self, name: str, arguments: dict[str, object] | None = None) -> str:
        """Run tool and return response."""
        result = await self.session.call_tool(
            name, arguments=arguments,
        )
        return result.content

    async def cleanup(self):
        """Clean up resources."""
        await self.exit_stack.aclose()


async def main():
    """Main entry point for the client."""
    client = MCPClient()

    try:
        print("\nConnecting to MCP server...")
        await client.connect_to_server("server.py", ["--advanced-tools", "--undetected-bot"])

        # tool = {"name": "start_browser"}
        # print(f"Tool: {tool}")
        # response = await client.run_tool(**tool)
        # print(f"\nResponse: {response}")

        # tool = {"name": "go_to", "arguments": {"url": "google.com"}}
        # print(f"Tool: {tool}")
        # response = await client.run_tool(**tool)
        # print(f"\nResponse: {response}")

        # tool = {"name": "go_to", "arguments": {"url": "https://www.bankofamerica.com/"}}
        # print(f"Tool: {tool}")
        # response = await client.run_tool(**tool)
        # print(f"\nResponse: {response}")

        tool = {"name": "go_to", "arguments": {"url": "https://www.google.com"}}
        print(f"Tool: {tool}")
        response = await client.run_tool(**tool)
        print(f"\nResponse: {response}")

        tool = {"name": "get_page_summary", "arguments": {"only_visible_elements": True}}
        print(f"Tool: {tool}")
        response = await client.run_tool(**tool)
        print(f"\nResponse: {response}")

        # tool = {"name": "go_to", "arguments": {"url": "bankofamerica.com"}}
        # print(f"Tool: {tool}")
        # response = await client.run_tool(**tool)
        # print(f"\nResponse: {response}")

        # tool = {"name": "take_screenshot", "arguments": {}}
        # print(f"Tool: {tool}")
        # response = await client.run_tool(**tool)
        # print(f"\nResponse: {response}")

    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
