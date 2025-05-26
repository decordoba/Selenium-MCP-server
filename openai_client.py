import argparse
import asyncio
import copy
import json
from contextlib import AsyncExitStack
import traceback

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


class MCPOpenAIClient:
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
        self.tools = []
        self.context = []
        self.messages = []
        self.logger = get_logger(self.__class__.__name__, file_name="client.log")
        self.stdio: object | None = None
        self.write: object | None = None

    async def connect_to_server(
        self, server_script_path: str = "server.py", server_script_args: list[str] = []
    ):
        """Connect to a MCP server.

        Args:
            server_script_path: Path to the server script.
            server_script_args: Arguments passed to the script, if any.
        """
        try:
            # Server configuration
            is_python = server_script_path.endswith(".py")
            is_js = server_script_path.endswith(".js")
            if not is_python and not is_js:
                raise ValueError("Server script must be a .py or .js file")
            command = "python" if is_python else "node"
            server_script_args = [server_script_args] if type(server_script_args) is str else server_script_args
            server_params = StdioServerParameters(
                command=command,
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
            self.logger.info(f"Connected to MCP server in {server_script_path}")
        except Exception as e:
            self.logger.error(f"Error connecting to MCP server: {e}")
            traceback.print_exc()
            raise

        # List available tools
        self.tools = await self.get_mcp_tools()
        self.logger.info(
            f"Available tools: {[tool['name'] for tool in self.tools]}"
        )

    async def get_mcp_tools(self) -> list[dict[str, object]]:
        """Get available tools from the MCP server in OpenAI format.

        Returns:
            A list of tools in OpenAI format.
        """
        try:
            tools_result = await self.session.list_tools()
            tools = []
            for tool in tools_result.tools:
                processed_params = tool.inputSchema
                del processed_params["title"]
                for property in processed_params["properties"]:
                    del processed_params["properties"][property]["title"]
                processed_tool = {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": processed_params,
                }
                tools.append(processed_tool)
            return tools
        except Exception as e:
            self.logger.error(f"Error getting MCP tools: {e}")
            raise

    async def process_query(self, query: str, reset_messages: bool = False, max_iterations: int | None = 10) -> str:
        """Process a query using OpenAI and available MCP tools.

        Args:
            query: The user query.

        Returns:
            The response from OpenAI.
        """
        # Update available tools
        tools = await self.get_mcp_tools()
        if tools != self.tools:
            self.tools = tools
            self.logger.info(f"Available tools updated: {[tool['name'] for tool in self.tools]}")
        else:
            self.logger.debug("No changes in tools")

        # Reset conversation history if needed
        if reset_messages:
            self.messages = []

        # Add user message to the conversation
        self.messages.append({"role": "user", "content": query})
        self.logger.info(f"Received query: {query}")

        # OpenAI API call
        iterations = 0
        while True:
            # Ensure the process ends if it takes too long
            iterations += 1
            if iterations > max_iterations:
                self.logger.error(f"Max iterations {max_iterations} reached")
                raise RuntimeError(f"Max iterations {max_iterations} reached)")

            # Call LLM
            try:
                self.logger.info("Calling OpenAI LLM")
                self.logger.debug(f"Model: {self.model}")
                self.logger.debug(f"Context: {self.context}")
                self.logger.debug(f"Messages: {self.messages}")
                self.logger.debug(f"Tools: {self.tools}")
                response = await self.openai_client.responses.create(
                    model=self.model,
                    input=self.context + self.messages,
                    tools=self.tools,
                    tool_choice="auto",
                    store=False,
                )
            except Exception as e:
                self.logger.error(f"Error calling OpenAI LLM: {e}")
                raise

            # Process LLM response and add to self.messages
            function_calls = []
            try:
                self.logger.info(f"Received {len(response.output)} responses")
                for i, assistant_output in enumerate(response.output):
                    if assistant_output.type == "function_call":
                        self.messages.append({
                            "type": "function_call",
                            "call_id": assistant_output.call_id,
                            "name": assistant_output.name,
                            "arguments": assistant_output.arguments,
                        })
                        function_calls.append(self.messages[-1])
                        self.logger.info(f"{i + 1}. Function: {assistant_output.name}, args: {assistant_output.arguments}")
                    elif assistant_output.type == "message":
                        if len(assistant_output.content) == 1 and assistant_output.content[0].type == "output_text":
                            self.messages.append({"role": "assistant", "content": assistant_output.content[0].text})
                            self.logger.info(f"{i + 1}. Message: {assistant_output.content[0].text}")
                        else:
                            self.messages.append({"role": "assistant", "content": assistant_output.content})
                            self.logger.warning(f"Received response message with unexpected format: {assistant_output.content}")
                            self.logger.info(f"{i + 1}. Message: {assistant_output.content}")
                    else:
                        self.messages.append(assistant_output)
                        self.logger.warning(f"Received response of unknown type {assistant_output.type}: {assistant_output}")
                        self.logger.info(f"{i + 1}. Response: {assistant_output}")
                    self.logger.debug(f"Response {i + 1}/{len(response.output)}: {self.messages[-1]}")
            except Exception as e:
                self.logger.error(f"Error processing LLM response: {e}")
                raise

            # If all functions have been called, end
            if len(function_calls) == 0:
                self.logger.debug("No function calls left to resolve")
                break

            # Call every function
            try:
                self.logger.info(f"Calling {len(function_calls)} functions")
                for i, tool_call in enumerate(function_calls):
                    self.logger.debug(f"Function {i + 1}/{len(function_calls)} request: {tool_call}")
                    # Execute function call
                    result = await self.session.call_tool(
                        tool_call["name"],
                        arguments=json.loads(tool_call["arguments"]),
                    )
                    self.logger.debug(f"Function {i + 1}/{len(function_calls)} response: {result}")

                    # Add tool response to conversation
                    message = {
                        "type": "function_call_output",
                        "call_id": tool_call["call_id"],
                        "output": [content.text for content in result.content],
                    }
                    message["output"] = message["output"][0] if len(message["output"]) == 1 else "[" + ", ".join(message["output"]) + "]"
                    if message["output"].startswith("base64,"):
                        image_message = {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": f"Image returned by function with call id {tool_call['call_id']}"},
                                {"type": "input_image", "image_url": f"data:image/png;{message['output']}"},
                            ],
                        }
                        message["output"] = "Image passed in the next message as an input_image"
                        self.messages.append(message)
                        self.messages.append(image_message)
                        self.logger.info(f"{i + 1}. Response: {message['output']}")
                        log_image_message = copy.deepcopy(image_message)
                        log_image_message["content"][1]["image_url"] = log_image_message["content"][1]["image_url"][:50] + "..."
                        self.logger.info(f"{i + 1}. Extra response: {log_image_message['content']}")
                    else:
                        self.messages.append(message)
                        self.logger.info(f"{i + 1}. Response: {message['output']}")
            except Exception as e:
                self.logger.error(f"Error calling LLM functions: {e}")
                raise

        return str(self.messages[-1]["content"]) if "content" in self.messages[-1] else str(self.messages[-1])

    async def cleanup(self):
        """Clean up resources."""
        await self.exit_stack.aclose()

    def set_instructions(self, instructions: str | None = None):
        """Set instructions for LLM."""
        if instructions is None:
            self.context = []
        else:
            self.context = [{"role": "system", "content": instructions}]
        self.logger.info(f"Updated context: {instructions}")

    def get_conversation(self) -> str:
        """Get conversation history."""
        return self.messages


async def main(advanced_tools: bool = False, undetected_bot: bool = False):
    """Main entry point for the client."""
    model = "gpt-4.1-nano"
    client = MCPOpenAIClient(model=model)

    args = []
    if advanced_tools:
        args.append("--advanced-tools")
    if undetected_bot:
        args.append("--undetected-bot")

    try:
        await client.connect_to_server("server.py", *args)

        client.set_instructions("""
Your goal is to complete tasks using the tools provided to control a browser.
You can request multiple functions at once, and they will be executed one after the other.
Continue calling tools until the task is completed or you are unable to finish it, only then communicate back to the user.
Your average workflow will be: `go_to` url, `get_page_summary` to understand contents page, `type_text` in element,
`click` in element, then `get_page_summary`, etc. Use only valid CSS selectors for the `locator` of `click` and `type_text`.
Examples: click(locator="#submit-button") or type_text(locator="input[name='email']", text="user@example.com").
You can also see the page with take_screenshot_as_base64, but always try get_page_summary first.
If get_page_summary does not return all elements in the page, use skip_elements to see the next elements.
Example: get_page_summary(skip_elements=20).
Or use filter_type to see only buttons, forms, links, or texts.
Example: get_page_summary(filter_type="button").
If a request to download is received, it probably means to download a file using the browser.
If you are asked a request that you don't know how to complete, searching in Google or Bing is a good start.
If you can't interact with an element, maybe there is something preventing you. Look at the summary and try to solve it before.
        """.strip().replace("\n", " "))

        while True:
            print("--------------------------")
            print("Enter message, or type QUIT to end:")
            query = input(">> ")
            if query.startswith("QUIT"):
                break

            response = await client.process_query(query)

            print(f"<< {response}")

        print(f"\nConversation history: {client.get_conversation()}")
    finally:
        await client.cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Chat with a Chat GPT  with browser navigation capabilities through Selenium"
    )
    parser.add_argument("--advanced-tools", action="store_true",
                        help="Enable selenium advanced tools by default")
    parser.add_argument("--undetected-bot", action="store_true",
                        help="Attempt to hide that selenium is a bot")
    args = parser.parse_args()

    asyncio.run(main(advanced_tools=args.advanced_tools, undetected_bot=args.undetected_bot))
