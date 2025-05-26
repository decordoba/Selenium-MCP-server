import asyncio
import json
from contextlib import AsyncExitStack

import nest_asyncio
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI

from logger import get_logger

# Apply nest_asyncio to allow nested event loops (needed for Jupyter/IPython)
nest_asyncio.apply()

# Load environment variables
load_dotenv()


class SimpleMCPOpenAIClient:
    """Client for interacting with OpenAI models using MCP tools."""

    def __init__(self, model: str = "gpt-4o"):
        """Initialize the OpenAI MCP client.

        Args:
            model: The OpenAI model to use.
        """
        # Initialize session and client objects
        self.session: ClientSession | None = None
        self.exit_stack = AsyncExitStack()
        self.openai_client = AsyncOpenAI()
        self.model = model
        self.logger = get_logger(self.__class__.__name__, file_name="client.log")
        self.stdio: object | None = None
        self.write: object | None = None

    async def connect_to_server(
        self,
        server_script_path: str = "server.py",
        server_script_args: list[str] | None = None,
    ):
        """Connect to a MCP server.

        Args:
            server_script_path: Path to the server script.
            server_script_args: Arguments passed to the script, if any.
        """
        # Server configuration
        server_script_args = [] if server_script_args is None else server_script_args
        server_script_args = (
            [server_script_args]
            if type(server_script_args) is str
            else server_script_args
        )
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
        self.logger.info("Connected to server with tools:")
        for tool in tools_result.tools:
            self.logger.info(f"  - {tool.name}: {tool.description}")

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

    async def process_query(self, query: str) -> str:
        """Process a query using OpenAI and available MCP tools.

        Args:
            query: The user query.

        Returns:
            The response from OpenAI.
        """
        # Get available tools
        tools = await self.get_mcp_tools()

        # Create conversation
        messages = [{"role": "user", "content": query}]

        # Initial OpenAI API call
        response = await self.openai_client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        # Get assistant's response
        assistant_message = response.choices[0].message

        # Append response to conversation
        messages.append(assistant_message)

        # Handle tool calls if present
        if assistant_message.tool_calls:
            # Process each tool call
            for tool_call in assistant_message.tool_calls:
                # Execute tool call
                result = await self.session.call_tool(
                    tool_call.function.name,
                    arguments=json.loads(tool_call.function.arguments),
                )

                # Add tool response to conversation
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": [content.text for content in result.content],
                    }
                )

            # Get final response from OpenAI with tool results
            final_response = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="none",  # Don't allow more tool calls
            )

            # Add response to conversation
            assistant_final_message = final_response.choices[0].message
            messages.append(assistant_final_message)

            return final_response.choices[0].message.content, messages

        # No tool calls, just return the direct response
        return assistant_message.content, messages

    async def cleanup(self):
        """Clean up resources."""
        await self.exit_stack.aclose()


async def main():
    """Main entry point for the client."""
    model = "gpt-4.1-nano"
    client = SimpleMCPOpenAIClient(model=model)
    client.logger.info(f"\nGPT model: {model}")

    try:
        client.logger.info("\nConnecting to MCP server...")
        await client.connect_to_server("server.py", "--undetected-bot")

        # Example: Ask to navigate to Google
        query = "Navigate to Google"
        client.logger.info(f"\nQuery: {query}")

        response, conversation = await client.process_query(query)
        client.logger.info(f"\nResponse: {response}")
        client.logger.info(f"\nConversation: {conversation}")
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
