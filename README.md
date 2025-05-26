# Selenium MCP Server

A Model Context Protocol server that provides selenium capabilities. This server enables LLMs to access a Chrome browser through selenium and interact with any URL with clicks, like a user would. I have also provided some code to integrate it with Chat GPT.

## Files available

* `server.py`: MCP server with tools to open a Selenium browser and interact with it. See tools available below.

* `openai_client.py`: Chat with Chat GPT. Chat GPT has access to the basic Selenium MCP tools. You can request actions, see what it does, provide feedback and ask for follow-ups once the task has been completed. Run it with:
```bash
uv run python openai_client.py
```

* `tool_client.py`: Call Selenium tools in MCP server directly.
```python
tool = {"name": "go_to", "arguments": {"url": "google.com"}}
response = await client.run_tool(**tool)
print(f"Tool: {tool}")
print(f"\nResponse: {response}")
```

* `simple_openai_client.py`: Request a task (especified by in this file) to Chat GPT. Chat GPT has access to the basic Selenium MCP tools. As soon as Chat GPT stops making function calls, execution ends.

## Tools
### Available Tools

- `go_to` - Navigate the browser to a specific URL.
  - Required arguments:
    - `url` (string): The URL to navigate to.

- `back` - Go back in browser history.
  - Returns: A message with the new URL.

- `get_current_url` - Get the current URL from the browser.
  - Returns: The current URL string.

- `click` - Click an element by locator.
  - Required arguments:
    - `locator` (string): The CSS/XPath/etc. selector.
  - Optional arguments:
    - `by` (string): How to locate the element. Default: `'css selector'`.

- `type_text` - Type text into an input field.
  - Required arguments:
    - `locator` (string): The selector for the input field.
    - `text` (string): The text to type.
  - Optional arguments:
    - `clear` (bool): Whether to clear existing text before typing. Default: `True`.
    - `press_enter` (bool): Whether to press Enter after typing. Default: `False`.
    - `by` (string): How to locate the element. Default: `'css selector'`.

- `get_page_summary` - Get a summary of the current page, including forms, buttons, links, and text elements.  
  - Optional arguments:  
    - `max_elements` (int): Maximum number of elements to return. Default: `20`.  
    - `skip_elements` (int): Number of elements to skip from the start. Default: `0`.  
    - `filter_type` (string | None): If specified, only include elements of this type (`"form"`, `"button"`, `"link"`, or `"text"`). Default: `None`.  
    - `only_visible_elements` (bool): Whether to include only visible elements. Default: `True`.  
  - Returns: A list of dictionaries with metadata for each element, including tag type, text, attributes, xpath, visibility, and hierarchy.

- `take_screenshot_as_base64` - Take a screenshot of the current page and return it as a base64-encoded string.  
  - Optional arguments:  
    - `compress` (bool): Whether to compress the image before returning. Default: `True`.  
  - Returns: A base64 string (prefixed with `base64,`) representing the screenshot. Saves the image to file as well. In case of an error, returns an error message.

- `enable_advanced_tools` - Enable access to the advanced tools.
  - Returns: A message confirming that advanced tools are now enabled. If already enabled, returns a notice.

### Advanced Tools (disabled by default)
- `forward` - Go forward in browser history.
  - Returns: A message with the new URL.

- `clear_text` - Clear text from an input element.
  - Required arguments:
    - `locator` (string): The selector for the element.
  - Optional arguments:
    - `by` (string): Selector strategy. Default: `'css selector'`.

- `get_element_text` - Get the visible text inside an element.
  - Required arguments:
    - `locator` (string): The element to target.
  - Optional arguments:
    - `by` (string): Selector strategy. Default: `'css selector'`.

- `get_element_attribute` - Get a specific attribute from an element.
  - Required arguments:
    - `locator` (string): The element to target.
    - `attribute` (string): The name of the attribute to retrieve.
  - Optional arguments:
    - `by` (string): Selector strategy. Default: `'css selector'`.

- `get_visible_text` - Extract readable text from an element.
  - Optional arguments:
    - `locator` (string): Element selector. Default: `'html'`.
    - `by` (string): Selector strategy. Default: `'css selector'`.

- `get_visible_text_xpath` - Get the HTML tree of the element that contains the given visible text.
  - Required arguments:
    - `visible_text` (string): The text to find.
  - Optional arguments:
    - `partial` (bool): Whether to allow partial match. Default: `False`.
    - `prettify` (bool): Format output with indentation.

- `get_html` - Get the HTML of an element, optionally limiting depth.
  - Optional arguments:
    - `locator` (string): Element selector. Default: `'html'`.
    - `depth` (int): How deep into the HTML tree to go. Use `-1` for unlimited. Default: `1`.
    - `by` (string): Selector strategy. Default: `'css selector'`.
    - `outer` (bool): Whether to include the tag itself. Default: `True`.
    - `prettify` (bool): Format output with indentation.

- `get_html_xpath` - Traverse and return the parent HTML tree of a given element.
  - Required arguments:
    - `locator` (string): The element to target.
  - Optional arguments:
    - `by` (string): Selector strategy. Default: `'css selector'`.
    - `prettify` (bool): Format output with indentation.

- `find_elements` - Return a list of matching elements with basic info.
  - Required arguments:
    - `locator` (string): Selector for the elements.
  - Optional arguments:
    - `by` (string): Selector strategy. Default: `'css selector'`.
    - `max_elements` (int): Limit the number of returned elements. Default: `10`.

- `count_elements` - Count the number of elements matching the locator.
  - Required arguments:
    - `locator` (string): The selector.
  - Optional arguments:
    - `by` (string): Selector strategy. Default: `'css selector'`.

- `element_exists` - Check if an element exists on the page.
  - Required arguments:
    - `locator` (string): The selector.
  - Optional arguments:
    - `by` (string): Selector strategy. Default: `'css selector'`.

- `start_browser` - Start the browser if it's not already running.
  - Returns: A message indicating if the browser was started or already running.

- `quit_browser` - Quit the browser if it is running.
  - Returns: A message indicating if the browser was closed or none was running.

- `set_timeout` - Set the default timeout used for waiting on elements.
  - Required arguments:
    - `seconds` (int): Timeout in seconds.

- `change_browser` - Switch to a different browser (optionally quitting the current one).
  - Optional arguments:
    - `browser` (string): One of `'chrome'`, `'firefox'`, `'safari'`, `'edge'`, `'ie'`.

- `get_title` - Get the current page title.
  - Returns: The title as a string.

- `refresh` - Refresh the current page.
  - Returns: A message with the refreshed URL.

- `execute_script` - Run raw JavaScript in the browser.
  - Required arguments:
    - `script` (string): JavaScript code to execute.
  - Optional arguments:
    - `*args`: Optional arguments passed to the script.

- `take_screenshot` - Save a screenshot of the current page.
  - Optional arguments:
    - `filename` (string): Name of the screenshot file. If not provided, a timestamped filename is used.

- `get_cookies` - Get all cookies from the current browser session.

- `set_cookie` - Add a cookie to the current session.
  - Required arguments:
    - `name` (string): Cookie name.
    - `value` (string): Cookie value.
  - Optional keyword arguments:
    - Other cookie parameters (e.g., `domain`, `path`, `secure`, etc.).

- `delete_cookies` - Delete all cookies from the session.

- `submit_form` - Submit a form element.
  - Required arguments:
    - `form_locator` (string): Selector for the form element.
  - Optional arguments:
    - `by` (string): Selector strategy. Default: `'css selector'`.

- `wait_for_element` - Wait until an element is present.
  - Required arguments:
    - `locator` (string): Selector for the element.
  - Optional arguments:
    - `by` (string): Selector strategy. Default: `'css selector'`.
    - `timeout` (int): Override default timeout.

- `wait_for_text` - Wait until specific text is present in the page.
  - Required arguments:
    - `text` (string): The text to wait for.
  - Optional arguments:
    - `timeout` (int): Override default timeout.

- `record_last_action` - Add the last executed action to the recording list.
  - Returns: A confirmation message. If no action has been performed, returns an error message.

- `save_recording` - Save the list of recorded actions to a JSON file.
  - Optional arguments:
    - `reset_recording` (bool): Whether to reset the recorded sequence after saving. Default: `True`.
  - Returns: A message confirming the file save, or an error message if the save failed.

- `load_recording` - Load a previously saved recording from a JSON file.
  - Required arguments:
    - `filename` (string): Name of the file to load from (within the recordings folder).
  - Returns: A message confirming the number of actions loaded or an error message if loading failed.

- `play_recording` - Replay all actions in the current recording.
  - Optional arguments:
    - `delay` (float): Number of seconds to wait between each action. Default: `0.0`.
  - Returns: A message confirming successful playback or an error message.

- `reset_recording` - Clear the current recording and last action.
  - Returns: A message confirming that the recording has been reset.

- `get_last_action` - Get the last action that was executed.
  - Returns: A message with the name and parameters of the last action.

- `get_recording` - Get the current sequence of recorded actions.
  - Returns: A message with the full list of recorded steps.

## Installation

### Using uv (recommended)

When using [`uv`](https://docs.astral.sh/uv/) no specific installation is needed. We will
use [`uvx`](https://docs.astral.sh/uv/guides/tools/) to directly run *mcp-server-selenium*.

These are the main commands:
```bash
# create environment
uv venv

# activate environment (Windows)
.venv\Scripts\activate.bat

# activate environment (Linux/Mac)
source .venv\Scripts\activate

# test the server from the browser with MCP Inspector
mcp dev server.py

# install the server to use with Claude (requires Claude Desktop)
mcp install server.py
``` 

### Using PIP

Alternatively you can install `mcp-server-selenium` via pip:

```bash
# call from level of pyproject.toml
pip install .
```

After installation, you can run it as a script using:

```bash
python -m mcp_server_selenium
```

## Configuration

### Configure for Claude.app

Add to your Claude settings:

<details>
<summary>Using uvx</summary>

```json
{
  "mcpServers": {
    "time": {
      "command": "uvx",
      "args": ["mcp-server-selenium"]
    }
  }
}
```
</details>

<details>
<summary>Using docker</summary>

```json
{
  "mcpServers": {
    "time": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "mcp/selenium"]
    }
  }
}
```
</details>

<details>
<summary>Using pip installation</summary>

```json
{
  "mcpServers": {
    "time": {
      "command": "python",
      "args": ["-m", "mcp_server_selenium"]
    }
  }
}
```
</details>

### Configure for Zed

Add to your Zed settings.json:

<details>
<summary>Using uvx</summary>

```json
"context_servers": [
  "mcp-server-selenium": {
    "command": "uvx",
    "args": ["mcp-server-selenium"]
  }
],
```
</details>

<details>
<summary>Using pip installation</summary>

```json
"context_servers": {
  "mcp-server-selenium": {
    "command": "python",
    "args": ["-m", "mcp_server_selenium"]
  }
},
```
</details>

### Configure for VS Code

For quick installation, use one of the one-click install buttons below...

[![Install with UV in VS Code](https://img.shields.io/badge/VS_Code-UV-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=selenium&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22mcp-server-selenium%22%5D%7D) [![Install with UV in VS Code Insiders](https://img.shields.io/badge/VS_Code_Insiders-UV-24bfa5?style=flat-square&logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=selenium&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22mcp-server-selenium%22%5D%7D&quality=insiders)

[![Install with Docker in VS Code](https://img.shields.io/badge/VS_Code-Docker-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=selenium&config=%7B%22command%22%3A%22docker%22%2C%22args%22%3A%5B%22run%22%2C%22-i%22%2C%22--rm%22%2C%22mcp%2Fselenium%22%5D%7D) [![Install with Docker in VS Code Insiders](https://img.shields.io/badge/VS_Code_Insiders-Docker-24bfa5?style=flat-square&logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=selenium&config=%7B%22command%22%3A%22docker%22%2C%22args%22%3A%5B%22run%22%2C%22-i%22%2C%22--rm%22%2C%22mcp%2Fselenium%22%5D%7D&quality=insiders)

For manual installation, add the following JSON block to your User Settings (JSON) file in VS Code. You can do this by pressing `Ctrl + Shift + P` and typing `Preferences: Open User Settings (JSON)`.

Optionally, you can add it to a file called `.vscode/mcp.json` in your workspace. This will allow you to share the configuration with others.

> Note that the `mcp` key is needed when using the `mcp.json` file.

<details>
<summary>Using uvx</summary>

```json
{
  "mcp": {
    "servers": {
      "selenium": {
        "command": "uvx",
        "args": ["mcp-server-selenium"]
      }
    }
  }
}
```
</details>

<details>
<summary>Using Docker</summary>

```json
{
  "mcp": {
    "servers": {
      "selenium": {
        "command": "docker",
        "args": ["run", "-i", "--rm", "mcp/selenium"]
      }
    }
  }
}
```
</details>

### Customization - Browser

By default, the server does not add some advanced tools. You can add them by passing the argument `--advanced-tools` to the `args` list in the configuration.

Example:
```json
{
  "command": "python",
  "args": ["-m", "mcp_server_selenium", "--advanced-tools"]
}
```

## Example Interactions

1. Get current time:
```json
{
  "name": "get_current_time",
  "arguments": {
    "timezone": "Europe/Warsaw"
  }
}
```
Response:
```json
{
  "timezone": "Europe/Warsaw",
  "datetime": "2024-01-01T13:00:00+01:00",
  "is_dst": false
}
```

2. Convert time between timezones:
```json
{
  "name": "convert_time",
  "arguments": {
    "source_timezone": "America/New_York",
    "time": "16:30",
    "target_timezone": "Asia/Tokyo"
  }
}
```
Response:
```json
{
  "source": {
    "timezone": "America/New_York",
    "datetime": "2024-01-01T12:30:00-05:00",
    "is_dst": false
  },
  "target": {
    "timezone": "Asia/Tokyo",
    "datetime": "2024-01-01T12:30:00+09:00",
    "is_dst": false
  },
  "time_difference": "+13.0h",
}
```

## Debugging

You can use the MCP inspector to debug the server.

The easy way:

```bash
uv run mcp dev mcp_server_selenium\server.py
```

For uvx installations:

```bash
npx @modelcontextprotocol/inspector uvx mcp-server-selenium
```

Or if you've installed the package in a specific directory or are developing on it:

```bash
cd path/to/servers/src/selenium
npx @modelcontextprotocol/inspector uv run mcp-server-selenium
```

## Examples of Commands for Claude

1. "Open Google.com"
2. "Search for elephants in Google"
3. "Read the top 5 articles on elephants in Google and summarize them"
4. "Fill the form in https://my_form.com with random responses"

## Build

Docker build:

```bash
cd selenium
docker build -t mcp/mcp_server_selenium .
```
