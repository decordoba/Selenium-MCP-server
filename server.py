import base64
import inspect
import io
import json
import os
import re
import time
from enum import Enum
from random import random

import undetected_chromedriver as uc
from bs4 import BeautifulSoup, NavigableString, Tag
from mcp.server.fastmcp import FastMCP
from PIL import Image
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from logger import get_logger


class Browser(str, Enum):
    CHROME = "chrome"
    EDGE = "edge"
    FIREFOX = "firefox"
    IE = "ie"
    SAFARI = "safari"


BROWSER_OPTIONS = [browser.value for browser in Browser]
BY_OPTIONS = [v for k, v in vars(By).items() if not (k.startswith("__") or callable(v))]
CHROME_LOCATION = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"


def compress_base64_image(
    base64_str: str, max_width: int = 800, max_height: int = 600
) -> str:
    """Resize image down, so that width or height match max_width/max_height."""
    image_data = base64.b64decode(base64_str)
    image = Image.open(io.BytesIO(image_data))

    # Resize while maintaining aspect ratio
    if image.width > max_width or image.height > max_height:
        ratio = min(max_width / image.width, max_height / image.height)
        new_size = (int(image.width * ratio), int(image.height * ratio))
        image = image.resize(new_size, resample=Image.Resampling.LANCZOS)

    # Save to new bytes buffer as PNG
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)

    # Encode to base64
    return base64.b64encode(buffer.read()).decode("utf-8")


def extract_html_to_depth(html: str, depth: int | None, prettify: bool = False) -> str:
    """Extract HTML only to a certain depth."""
    soup = BeautifulSoup(html, "html.parser")
    if depth is None:
        return soup.prettify if prettify else str(soup)
    result = ""
    for child in soup.contents:
        trimmed = trim_html_tag_to_depth(child, depth)
        if trimmed:
            if prettify and isinstance(trimmed, Tag):
                result += trimmed.prettify()
            else:
                result += str(trimmed)
    return result


def trim_html_tag_to_depth(
    tag: Tag | NavigableString | None, depth: int
) -> Tag | NavigableString | None:
    """Trim HTML tag to a maximum depth."""
    if depth <= 0 or tag is None:
        return None
    if isinstance(tag, NavigableString):
        return tag
    new_tag = clone_tag_shallow(tag)
    if depth > 1:
        for child in tag.children:
            trimmed_child = trim_html_tag_to_depth(child, depth - 1)
            if trimmed_child:
                new_tag.append(trimmed_child)
    return new_tag


def clone_tag_shallow(tag: Tag) -> Tag:
    """Clone a tag without children, preserving tag name and attributes."""
    new_tag = BeautifulSoup("", "html.parser").new_tag(tag.name)
    for attr, val in tag.attrs.items():
        new_tag[attr] = val
    return new_tag


class SeleniumMCPServer:
    def __init__(self, browser: str = Browser.CHROME.value, timeout: int = 10):
        """Initialize class, and create mcp server."""
        # Create an MCP server
        self.mcp = FastMCP(
            name="selenium",
            host="0.0.0.0",  # only used for SSE transport
            port=8050,  # only used for SSE transport
        )

        # Declare variables
        self.browser = browser
        self.driver = None
        self.undetected = False  # only compatible with chrome
        self.timeout = timeout  # seconds
        self.advanced_tools_enabled = False
        self.screenshots_dir = os.path.join(os.getcwd(), "screenshots")
        self.recordings_dir = os.path.join(os.getcwd(), "recordings")
        self.logger = get_logger("SeleniumMCPServer", file_name="server.log")
        self.sequence_recorded = []
        self.last_action = None

        self._register_tools(advanced_tools=False)

    def _register_tools(self, advanced_tools: bool = False):
        """Register selenium tools (either main or advanced tools) with MCP."""
        # Basic browser navigation
        if not advanced_tools:
            self.mcp.tool()(self.go_to)
            self.mcp.tool()(self.back)
            self.mcp.tool()(self.get_current_url)
        else:
            self.mcp.tool()(self.forward)
            self.mcp.tool()(self.refresh)
            self.mcp.tool()(self.get_title)

        # Browser management
        if not advanced_tools:
            pass
        else:
            self.mcp.tool()(self.start_browser)
            self.mcp.tool()(self.quit_browser)
            self.mcp.tool()(self.set_timeout)
            self.mcp.tool()(self.change_browser)

        # Element interaction
        if not advanced_tools:
            self.mcp.tool()(self.click)
            self.mcp.tool()(self.type_text)
        else:
            self.mcp.tool()(self.clear_text)

        # Page html extraction
        if not advanced_tools:
            self.mcp.tool()(self.get_page_summary)
        else:
            self.mcp.tool()(self.get_html)
            self.mcp.tool()(self.get_element_text)
            self.mcp.tool()(self.get_element_attribute)
            self.mcp.tool()(self.get_element_xpath)
            self.mcp.tool()(self.get_element_html)
            self.mcp.tool()(self.get_visible_text)
            self.mcp.tool()(self.get_visible_text_xpath)

        # Element finding
        if not advanced_tools:
            pass
        else:
            self.mcp.tool()(self.find_elements)
            self.mcp.tool()(self.count_elements)
            self.mcp.tool()(self.element_exists)

        # Screenshots
        if not advanced_tools:
            self.mcp.tool()(self.take_screenshot_as_base64)
        else:
            self.mcp.tool()(self.take_screenshot)

        # JavaScript execution
        if advanced_tools:
            self.mcp.tool()(self.execute_script)

        # Cookies
        if advanced_tools:
            self.mcp.tool()(self.get_cookies)
            self.mcp.tool()(self.set_cookie)
            self.mcp.tool()(self.delete_cookies)

        # Advanced interactions
        if advanced_tools:
            self.mcp.tool()(self.submit_form)
            self.mcp.tool()(self.wait_for_element)
            self.mcp.tool()(self.wait_for_text)

        # Record sequence utils
        if advanced_tools:
            self.mcp.tool()(self.get_last_action)
            self.mcp.tool()(self.get_recording)
            self.mcp.tool()(self.record_last_action)
            self.mcp.tool()(self.save_recording)
            self.mcp.tool()(self.load_recording)
            self.mcp.tool()(self.reset_recording)
            self.mcp.tool()(self.play_recording)

        # Option to enable advanced tools
        if not advanced_tools:
            self.mcp.tool()(self.enable_advanced_tools)
        if advanced_tools:
            self.advanced_tools_enabled = True

    def _ensure_browser_started(self):
        """Make sure the browser is started before any operation."""
        if self.driver is None:
            self.start_browser()

    def _wait_if_undetected(self, offset: int = 1, variance: int = 4):
        """Wait between offset and offset+variance seconds.

        Only applied if self.undetected is True.
        """
        if self.undetected:
            wait_seconds = offset + variance * random()
            time.sleep(wait_seconds)

    def _log_return(self, return_value: object | None = None):
        """Log return of a function."""
        self.logger.info(f"Return: {str(return_value)}", stacklevel=2)
        return return_value

    def _log_call(self, message: str):
        """Log call to a function."""
        self.logger.info(f"Call: {str(message)}", stacklevel=2)
        return message

    def _remember_action(self):
        """Store action to be used later in recording."""
        frame = inspect.stack()[1].frame
        func_name = frame.f_code.co_name
        args_info = inspect.getargvalues(frame)
        args_dict = {arg: args_info.locals[arg] for arg in args_info.args}
        if "self" in args_dict:
            del args_dict["self"]
        self.last_action = (func_name, args_dict)

    def start_browser(self) -> str:
        """Start the browser if not already running."""
        self._log_call(f"Start browser {self.browser} (undetected: {self.undetected})")
        if self.driver is None:
            if self.browser == Browser.CHROME:
                if self.undetected:
                    self.driver = uc.Chrome(browser_executable_path=CHROME_LOCATION)
                else:
                    options = Options()
                    options.binary_location = CHROME_LOCATION
                    self.driver = webdriver.Chrome(
                        service=Service(ChromeDriverManager().install()),
                        options=options,
                    )
            elif self.browser == Browser.EDGE:
                self.driver = webdriver.Edge()
            elif self.browser == Browser.FIREFOX:
                self.driver = webdriver.Firefox()
            elif self.browser == Browser.IE:
                self.driver = webdriver.Ie()
            elif self.browser == Browser.SAFARI:
                self.driver = webdriver.Safari()
            else:
                return self._log_return(f"Unknown browser {self.browser}")
            self.driver.maximize_window()
            return self._log_return(f"Started {self.browser} browser")
        return self._log_return(f"{self.browser.capitalize()} browser already running")

    def quit_browser(self) -> str:
        """Quit the browser if running."""
        self._log_call(f"Quit browser {self.browser} (undetected: {self.undetected})")
        if self.driver is not None:
            self.driver.quit()
            self.driver = None
            return self._log_return(
                f"{self.browser.capitalize()} browser closed successfully"
            )
        return self._log_return("No browser running")

    def set_timeout(self, seconds: int) -> str:
        """Set the default timeout for wait operations."""
        self._remember_action()
        self._log_call(f"Set timeout to {seconds} seconds")
        self.timeout = seconds
        return self._log_return(f"Default timeout set to {seconds} seconds")

    def change_browser(self, browser: str = Browser.CHROME.value) -> str:
        """Quit the browser if running and change the browser used."""
        self._log_call(
            f"Change browser to {browser} from {self.browser} "
            f"(undetected: {self.undetected})"
        )
        if browser not in BROWSER_OPTIONS:
            return self._log_return(
                f"Invalid browser: {browser}. "
                f"Must be one of: {', '.join(BROWSER_OPTIONS)}"
            )
        self.quit_browser()
        self.browser = browser
        return self._log_return(f"Browser set to {browser}")

    def go_to(self, url: str) -> str:
        """Navigate to URL."""
        self._remember_action()
        self._log_call(f"Go to url '{url}'")
        self._ensure_browser_started()
        self._wait_if_undetected()
        if not url.startswith("http"):
            url = "http://" + url
        self.driver.get(url)
        return self._log_return(f"Navigated to {self.driver.current_url}")

    def get_current_url(self) -> str:
        """Return current URL."""
        self._log_call("Get current url")
        self._ensure_browser_started()
        return self._log_return(self.driver.current_url)

    def get_title(self) -> str:
        """Return page title."""
        self._log_call("Get title")
        self._ensure_browser_started()
        return self._log_return(self.driver.title)

    def refresh(self) -> str:
        """Refresh the current page."""
        self._log_call("Refresh page")
        self._ensure_browser_started()
        self._wait_if_undetected()
        self.driver.refresh()
        return self._log_return(f"Page refreshed to {self.driver.current_url}")

    def back(self) -> str:
        """Navigate back in browser history."""
        self._remember_action()
        self._log_call("Go back")
        self._ensure_browser_started()
        self._wait_if_undetected()
        self.driver.back()
        return self._log_return(f"Navigated back to {self.driver.current_url}")

    def forward(self) -> str:
        """Navigate forward in browser history."""
        self._remember_action()
        self._log_call("Go forward")
        self._ensure_browser_started()
        self._wait_if_undetected()
        self.driver.forward()
        return self._log_return(f"Navigated forward to {self.driver.current_url}")

    def click(self, locator: str, by: str = "css selector") -> str:
        """Click an element."""
        self._remember_action()
        self._log_call(f"Click element with locator: {locator}, by: {by}")
        self._ensure_browser_started()
        self._wait_if_undetected()
        if by not in BY_OPTIONS:
            return self._log_return(
                f"Invalid by: {by}. Must be one of: {', '.join(BY_OPTIONS)}"
            )
        try:
            element = WebDriverWait(self.driver, self.timeout).until(
                EC.element_to_be_clickable((by, locator))
            )
            element.click()
            return self._log_return(f"Clicked element: {locator}")
        except TimeoutException:
            return self._log_return(f"Timeout waiting for element {locator}")
        except Exception as e:
            return self._log_return(f"Error clicking element: {str(e)}")

    def type_text(
        self,
        locator: str,
        text: str,
        clear: bool = True,
        press_enter: bool = False,
        is_password: bool = False,
        by: str = "css selector",
    ) -> str:
        """Type text into an element. Optional: clear text before, press ENTER after."""
        self._remember_action()
        self._log_call(
            f"Type text '{'****' if is_password else text}' "
            f"in element with locator: {locator}, by: {by}. "
            f"Clear: {clear}, Press ENTER: {press_enter}"
        )
        self._ensure_browser_started()
        self._wait_if_undetected()
        if by not in BY_OPTIONS:
            return self._log_return(
                f"Invalid by: {by}. Must be one of: {', '.join(BY_OPTIONS)}"
            )
        try:
            element = WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((by, locator))
            )
            if clear:
                element.clear()
                self._wait_if_undetected()
            element.send_keys(text)
            if press_enter:
                self._wait_if_undetected()
                element.send_keys(Keys.ENTER)
            return self._log_return(f"Typed '{text}' into {locator}")
        except TimeoutException:
            return self._log_return(f"Timeout waiting for element {locator}")
        except Exception as e:
            return self._log_return(f"Error typing text: {str(e)}")

    def clear_text(self, locator: str, by: str = "css selector") -> str:
        """Clear text from an element."""
        self._remember_action()
        self._log_call(f"Clear text in element with locator: {locator}, by: {by}")
        self._ensure_browser_started()
        self._wait_if_undetected()
        if by not in BY_OPTIONS:
            return self._log_return(
                f"Invalid by: {by}. Must be one of: {', '.join(BY_OPTIONS)}"
            )
        try:
            element = WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((by, locator))
            )
            element.clear()
            return self._log_return(f"Cleared text from {locator}")
        except TimeoutException:
            return self._log_return(f"Timeout waiting for element {locator}")
        except Exception as e:
            return self._log_return(f"Error clearing text: {str(e)}")

    def get_element_text(self, locator: str, by: str = "css selector") -> str:
        """Get text in an element."""
        self._log_call(f"Get text in element with locator: {locator}, by: {by}")
        self._ensure_browser_started()
        if by not in BY_OPTIONS:
            return self._log_return(
                f"Invalid by: {by}. Must be one of: {', '.join(BY_OPTIONS)}"
            )
        try:
            element = WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((by, locator))
            )
            return self._log_return(element.text)
        except TimeoutException:
            return self._log_return(f"Timeout waiting for element {locator}")
        except Exception as e:
            return self._log_return(f"Error getting text: {str(e)}")

    def get_element_attribute(
        self, locator: str, attribute: str, by: str = "css selector"
    ) -> str:
        """Get attribute value from an element."""
        self._log_call(
            f"Get attribute {attribute} in element with locator: {locator}, by: {by}"
        )
        self._ensure_browser_started()
        if by not in BY_OPTIONS:
            return self._log_return(
                f"Invalid by: {by}. Must be one of: {', '.join(BY_OPTIONS)}"
            )
        try:
            element = WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((by, locator))
            )
            return self._log_return(element.get_attribute(attribute) or "")
        except TimeoutException:
            return self._log_return(f"Timeout waiting for element {locator}")
        except Exception as e:
            return self._log_return(f"Error getting attribute: {str(e)}")

    def get_visible_text(self, locator: str = "html", by: str = "css selector") -> str:
        """Get visible text in an element."""
        self._log_call(f"Get visible text in element with locator: {locator}, by: {by}")
        html = self.get_element_attribute(locator=locator, attribute="outerHTML", by=by)
        text = BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)
        return self._log_return(re.sub(r"\n{3,}", "\n\n", text))

    def get_visible_text_xpath(
        self, visible_text: str, partial: bool = False, prettify: bool = False
    ) -> str:
        """Get parent element tree of a visible text."""
        self._log_call(
            f"Get xpath for visible text '{visible_text}'. "
            f"Partial: {partial}, prettify: {prettify}"
        )
        locator = f"//*[text()='{visible_text}']"
        if partial:
            locator = f"//*[contains(text()='{visible_text}')]"
        return self._log_return(
            self.get_element_xpath(locator, by=By.XPATH, prettify=prettify)
        )

    def get_html(self, depth: int = 1) -> str:
        """Get page HTML up to some depth (-1 for infinite depth)."""
        return self.get_element_html(depth=depth)

    def get_element_html(
        self,
        locator: str = "html",
        depth: int = 1,
        by: str = "css selector",
        outer: bool = True,
        prettify: bool = False,
    ) -> str:
        """Get HTML of an element, up to some depth (-1 for infinite depth)."""
        self._log_call(
            f"Get html with depth {depth} of element with locator: "
            f"{locator}, by: {by}. Outer: {outer}, prettify: {prettify}"
        )
        html = self.get_element_attribute(
            locator=locator, attribute="outerHTML" if outer else "innerHTML", by=by
        )
        depth = depth if depth >= 0 else None
        return self._log_return(extract_html_to_depth(html, depth, prettify=prettify))

    def get_element_xpath(
        self, locator: str, by: str = "css selector", prettify: bool = False
    ) -> str:
        """Get parent element tree of an element."""
        self._log_call(
            f"Get xpath of element with locator: {locator}, by: {by}. "
            f"Prettify: {prettify}"
        )
        try:
            element = WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((by, locator))
            )

            element_path = [element]
            while True:
                try:
                    parent = element.find_element(By.XPATH, "..")
                except Exception:
                    break
                element_path.insert(0, parent)
                element = parent

            root, cursor = None, None
            for el in element_path:
                html = el.get_attribute("outerHTML")
                new_tag = BeautifulSoup(html, "html.parser").find()
                if root is None:
                    root = new_tag
                    cursor = root
                else:
                    # Move to the deepest tag and insert the next
                    if cursor is not None:
                        cursor.clear()  # remove placeholder children
                        cursor.append(new_tag)
                        cursor = new_tag
            if root is None:
                return self._log_return("")
            return self._log_return(root.prettify() if prettify else str(root))
        except TimeoutException:
            return self._log_return(f"Timeout waiting for element {locator}")
        except Exception as e:
            return self._log_return(f"Error locating element: {str(e)}")

    def get_page_summary(
        self,
        skip_elements: int = 0,
        max_elements: int = 20,
        filter_type: str = "",
        only_visible_elements: bool = True,
        detailed: bool = False,
    ) -> list[dict[str, object]]:
        """Get page summary containing all forms, buttons, links and texts."""
        self._log_call(
            f"Get page summary. Only visible: {only_visible_elements}, "
            f"max elements: {max_elements}"
        )
        visibility_cache = {}

        def is_element_visible_by_xpath(xpath):
            if xpath in visibility_cache:
                return visibility_cache[xpath]
            try:
                el = self.driver.find_element(By.XPATH, xpath)
                visible = el.is_displayed()
            except NoSuchElementException:
                return False
            visibility_cache[xpath] = visible
            return visible

        def build_xpath(el):
            path = []
            while el and el.name != "[document]":
                sibs = el.find_previous_siblings(el.name)
                index = f"[{len(sibs) + 1}]" if sibs else ""
                path.insert(0, f"{el.name}{index}")
                el = el.parent
            return "/" + "/".join(path)

        def get_depth(el):
            depth = 0
            while el and el.name != "[document]":
                el = el.parent
                depth += 1
            return depth

        def clean_attrs(tag, attrs):
            data = {}
            for attr in attrs:
                value = tag.get(attr)
                if value:
                    data[attr.replace("-", "_")] = value
            return data

        def extract_inputs(form):
            inputs = []
            for inp in form.find_all(["input", "textarea", "select"]):
                inp_data = clean_attrs(
                    inp, ["name", "placeholder", "type", "class", "id"]
                )
                if "class" in inp_data:
                    inp_data["class"] = (
                        inp_data["class"] if detailed else " ".join(inp_data["class"])
                    )
                if inp_data:
                    xpath = build_xpath(inp)
                    if detailed:
                        inp_data["xpath"] = xpath
                    visible = is_element_visible_by_xpath(xpath)
                    if not only_visible_elements:
                        if detailed:
                            inp_data["visible"] = visible
                    elif not visible:
                        continue
                    inputs.append(inp_data)
            return inputs

        def extract_buttons(form):
            buttons = []
            for btn in form.find_all("button"):
                btn_data = {}
                text = btn.get_text(strip=True)
                if text:
                    btn_data["text"] = text
                if detailed:
                    btn_data.update(
                        clean_attrs(btn, ["aria-label", "role", "class", "id"])
                    )
                else:
                    btn_data.update(clean_attrs(btn, ["class", "id"]))
                classes = btn.get("class")
                if classes:
                    btn_data["class"] = classes if detailed else " ".join(classes)
                xpath = build_xpath(btn)
                if detailed:
                    btn_data["xpath"] = xpath
                visible = is_element_visible_by_xpath(xpath)
                if not only_visible_elements:
                    if detailed:
                        btn_data["visible"] = visible
                elif not visible:
                    continue
                if btn_data:
                    buttons.append(btn_data)
            return buttons

        def summarize_forms_buttons_links_and_text():
            summary = []
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            summary_tags = ["form", "button", "a", "h1", "h2", "h3", "p", "span"]
            for tag in soup.find_all(summary_tags):
                xpath = build_xpath(tag)
                data = {
                    "index": None,  # fill later
                    "type": (
                        "form"
                        if tag.name == "form"
                        else (
                            "button"
                            if tag.name == "button"
                            else "link" if tag.name == "a" else "text"
                        )
                    ),
                }
                if filter_type != "" and filter_type != data["type"]:
                    continue
                if detailed:
                    data["xpath"] = xpath
                    data["depth"] = get_depth(tag)
                visible = is_element_visible_by_xpath(xpath)
                if not only_visible_elements:
                    if detailed:
                        data["visible"] = visible
                elif not visible:
                    continue
                text = tag.get_text(strip=True)
                if text:
                    data["text"] = text
                if data["type"] == "link":
                    href = tag.get("href")
                    if href:
                        data["href"] = href
                elif data["type"] == "form":
                    inputs = extract_inputs(tag)
                    if inputs:
                        data["inputs"] = inputs
                    buttons = extract_buttons(tag)
                    if buttons:
                        data["buttons"] = buttons
                if detailed:
                    data.update(clean_attrs(tag, ["aria-label", "role"]))
                classes = tag.get("class")
                if classes:
                    data["class"] = classes if detailed else " ".join(classes)
                id = tag.get("id")
                if id:
                    data["id"] = id
                if detailed:
                    parent = tag.find_parent()
                    if parent and parent.name != "[document]":
                        parent_info = {
                            "tag": parent.name,
                            "id": parent.get("id"),
                            "class": parent.get("class"),
                        }
                        parent_info = {k: v for k, v in parent_info.items() if v}
                        if parent_info:
                            data["parent"] = parent_info
                summary.append(data)
            # Reorder to place most important items first
            order = {"button": 0, "link": 1, "form": 2, "text": 3}
            summary = sorted(summary, key=lambda x: order.get(x["type"], float("inf")))
            # Add index indicating number of total elements
            for i, data in enumerate(summary):
                data["index"] = f"{i + 1}/{len(summary)}"
            return summary

        summary = summarize_forms_buttons_links_and_text()
        return self._log_return(summary[skip_elements:skip_elements + max_elements])

    def find_elements(
        self,
        locator: str,
        by: str = "css selector",
        max_elements: int = 10,
        skip_elements: int = 0,
    ) -> list[dict[str, str]]:
        """Return info elements (up to max_elements, skip first skip_elements)."""
        self._log_call(
            f"Find elements with locator: {locator}, by: {by}. "
            f"Max: {max_elements}, skip: {skip_elements}"
        )
        self._ensure_browser_started()
        if by not in BY_OPTIONS:
            error = [
                {"error": f"Invalid by: {by}. Must be one of: {', '.join(BY_OPTIONS)}"}
            ]
            return self._log_return(error)
        try:
            elements = WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_all_elements_located((by, locator))
            )
            result = []
            for i, element in enumerate(
                elements[skip_elements:max_elements + skip_elements]
            ):
                try:
                    html = re.sub(
                        r"\n{3,}",
                        "\n\n",
                        BeautifulSoup(
                            element.get_attribute("outerHTML"), "html.parser"
                        ).get_text(separator="\n", strip=True),
                    )

                    result.append(
                        {
                            "index": i,
                            "text": element.text.strip(),
                            "html": html,
                            "tag": element.tag_name,
                            "id": element.get_attribute("id") or "",
                            "class": element.get_attribute("class") or "",
                        }
                    )
                except Exception:
                    pass
            return self._log_return(result)
        except TimeoutException:
            return self._log_return([])
        except Exception as e:
            return self._log_return([{"error": str(e)}])

    def count_elements(self, locator: str, by: str = "css selector") -> int:
        """Count elements matching the locator."""
        self._log_call(f"Count elements with locator: {locator}, by: {by}")
        self._ensure_browser_started()
        if by not in BY_OPTIONS:
            return self._log_return(-1)
        try:
            elements = self.driver.find_elements(by, locator)
            return self._log_return(len(elements))
        except Exception:
            return self._log_return(0)

    def element_exists(self, locator: str, by: str = "css selector") -> bool:
        """Check if element exists."""
        self._log_call(f"Elements exists with locator: {locator}, by: {by}")
        self._ensure_browser_started()
        if by not in BY_OPTIONS:
            return self._log_return(False)
        try:
            self.driver.find_element(by, locator)
            return self._log_return(True)
        except NoSuchElementException:
            return self._log_return(False)

    def execute_script(self, script: str, *args) -> str:
        """Execute JavaScript in the browser."""
        self._remember_action()
        self._log_call(f"Execute script: {script}. Arguments: {args}")
        self._ensure_browser_started()
        self._wait_if_undetected()
        try:
            result = self.driver.execute_script(script, *args)
            if result is None:
                return self._log_return("Script executed successfully")
            if isinstance(result, dict | list):
                return self._log_return(json.dumps(result))
            return self._log_return(str(result))
        except Exception as e:
            return self._log_return(f"Error executing script: {str(e)}")

    def _get_filename(self, prefix: str = "screenshot", extension: str = "png") -> str:
        """Get filename in standard style."""
        return (
            f"{prefix}_{time.strftime('%Y%m%d_%H%M%S', time.localtime())}.{extension}"
        )

    def _get_filepath(self, filename: str, directory: str) -> str:
        """Get full path and folder ready to save screenshot."""
        os.makedirs(directory, exist_ok=True)
        return os.path.join(directory, filename)

    def take_screenshot(self) -> str:
        """Take a screenshot of the current page."""
        self._remember_action()
        filename = self._get_filename()
        self._log_call(
            f"Take screenshot. Filename: {filename}, folder: {self.screenshots_dir}"
        )
        self._ensure_browser_started()
        try:
            filepath = self._get_filepath(filename, self.screenshots_dir)
            self.driver.save_screenshot(filepath)
            return self._log_return(f"Screenshot saved to {filepath}")
        except Exception as e:
            return self._log_return(f"Error taking screenshot: {str(e)}")

    def take_screenshot_as_base64(self, compress: bool = True) -> str:
        """Take a screenshot of the current page and return as base64."""
        self._remember_action()
        filename = self._get_filename()
        self._log_call(
            f"Take screenshot as base 64. "
            f"Filename: {filename}, folder: {self.screenshots_dir}"
        )
        self._ensure_browser_started()
        try:
            base64_string = self.driver.get_screenshot_as_base64()
            filepath = self._get_filepath(filename, self.screenshots_dir)
            image_data = base64.b64decode(base64_string)
            with open(filepath, "wb") as file:
                file.write(image_data)
            if compress:
                base64_string = compress_base64_image(base64_string)
                image_data = base64.b64decode(base64_string)
                filepath = filepath.replace(".png", "_compressed.png")
                with open(filepath, "wb") as file:
                    file.write(image_data)
            return_value = "base64," + base64_string
            self._log_return(
                return_value[:50] + "..." + return_value[-50:]
            )  # avoid occupying all logs
            return return_value
        except Exception as e:
            return self._log_return(f"Error taking screenshot: {str(e)}")

    def get_cookies(self) -> list[dict[str, object]]:
        """Get all browser cookies."""
        self._log_call("Get cookies")
        self._ensure_browser_started()
        return self._log_return(self.driver.get_cookies())

    def set_cookie(self, name: str, value: str, **kwargs) -> str:
        """Set a browser cookie."""
        self._remember_action()
        self._log_call(f"Set cookie '{name}': '{value}'. Arguments: {kwargs}")
        self._ensure_browser_started()
        self._wait_if_undetected()
        try:
            self.driver.add_cookie({"name": name, "value": value, **kwargs})
            return self._log_return(f"Cookie '{name}' set successfully")
        except Exception as e:
            return self._log_return(f"Error setting cookie: {str(e)}")

    def delete_cookies(self) -> str:
        """Delete all cookies."""
        self._remember_action()
        self._log_call("Delete all cookies")
        self._ensure_browser_started()
        self._wait_if_undetected()
        self.driver.delete_all_cookies()
        return self._log_return("All cookies deleted")

    def submit_form(self, form_locator: str, by: str = "css selector") -> str:
        """Submit a form."""
        self._remember_action()
        self._log_call(f"Submit form with form locator: {form_locator}, by: {by}")
        self._ensure_browser_started()
        self._wait_if_undetected()
        try:
            form = WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((by, form_locator))
            )
            form.submit()
            return self._log_return("Form submitted")
        except TimeoutException:
            return self._log_return(f"Timeout waiting for form {form_locator}")
        except Exception as e:
            return self._log_return(f"Error submitting form: {str(e)}")

    def wait_for_element(
        self, locator: str, by: str = "css selector", timeout: int = -1
    ) -> bool:
        """Wait for an element to be present, if timeout -1 use timeout set."""
        self._remember_action()
        self._log_call(
            f"Wait for element with locator: {locator}, by: {by} "
            f"(timeout: {timeout} seconds)"
        )
        self._ensure_browser_started()
        timeout = timeout or self.timeout
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, locator))
            )
            return self._log_return(True)
        except TimeoutException:
            return self._log_return(False)

    def wait_for_text(self, text: str, timeout: int = -1) -> bool:
        """Wait for text to be present on the page, if timeout -1 use timeout set."""
        self._remember_action()
        self._log_call(f"Wait for text '{text}' (timeout: {timeout} seconds)")
        self._ensure_browser_started()
        timeout = timeout or self.timeout
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.text_to_be_present_in_element(("css selector", "html"), text)
            )
            return self._log_return(True)
        except TimeoutException:
            return self._log_return(False)

    def get_last_action(self) -> str:
        """Get last action performed."""
        self._log_call("Get last action")
        return self._log_return(f"Last action: {self.last_action}")

    def get_recording(self) -> str:
        """Get recorded sequence."""
        self._log_call("Get recording")
        return self._log_return(f"Last action: {self.sequence_recorded}")

    def record_last_action(self) -> str:
        """Add last action to recorded sequence."""
        self._log_call("Record last action")
        if self.last_action is None:
            return self._log_return("Last action does not exist")
        self.sequence_recorded.append(self.last_action)
        return self._log_return(f"Action recorded: {self.last_action}")

    def save_recording(self, reset_recording: bool = True) -> str:
        """Save the recorded sequence to a JSON file."""
        filename = self._get_filename("recording", extension="txt")
        self._log_call(
            f"Save recording. Filename: {filename}, folder: {self.recordings_dir}"
        )
        try:
            filepath = self._get_filepath(filename, self.recordings_dir)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.sequence_recorded, f, ensure_ascii=False, indent=2)
            num_actions = len(self.sequence_recorded)
            if reset_recording:
                self.reset_recording()
            return self._log_return(
                f"Recording ({num_actions} actions) saved to {filepath}"
            )
        except Exception as e:
            return self._log_return(f"Error saving recording: {str(e)}")

    def load_recording(self, filename: str) -> str:
        """Load a recording into self.recorded_sequence from a JSON file."""
        filepath = self._get_filepath(filename, self.recordings_dir)
        self._log_call(
            f"Load recording. Filename: {filename}, folder: {self.recordings_dir}"
        )
        try:
            with open(filepath, encoding="utf-8") as f:
                self.sequence_recorded = json.load(f)
            num_actions = len(self.sequence_recorded)
            return self._log_return(
                f"Recording loaded ({num_actions} actions) from {filepath}"
            )
        except Exception as e:
            return self._log_return(f"Error loading recording: {str(e)}")

    def reset_recording(self) -> str:
        """Reset last_action and sequence_recorded."""
        self._log_call("Reset recording")
        self.last_action = None
        self.sequence_recorded = []
        return self._log_return("Recording has been reset")

    def play_recording(self, delay: float = 0.0) -> str:
        """Perform actions in current recording, with delay seconds between."""
        self._log_call(
            f"Play recording of {len(self.sequence_recorded)} actions. "
            f"Delay: {delay} seconds"
        )
        try:
            for action_name, arguments in self.sequence_recorded:
                getattr(self, action_name)(**arguments)
                if delay > 0:
                    time.sleep(delay)
            return self._log_return("Recording has been played")
        except Exception as e:
            return self._log_return(f"Error playing recording: {str(e)}")

    def enable_advanced_tools(self) -> str:
        """Enable advanced tools. Call if main tools are not sufficient."""
        self._log_call("Enable advanced tools")
        if self.advanced_tools_enabled:
            return self._log_return("Advanced tools already enabled")
        self._register_tools(advanced_tools=True)
        return self._log_return("Advanced tools enabled")

    def run(
        self,
        transport: str = "stdio",
        advanced_tools: bool = False,
        undetected_bot: bool = False,
    ):
        """Run the MCP server with the specified transport."""
        # Choose tools to register
        self._log_call("Run server")
        if advanced_tools:
            self._register_tools(advanced_tools=True)
        # Choose wether to use undetected mode
        self.undetected = undetected_bot
        # Register MCP tools
        if transport == "stdio":
            self.mcp.run(transport="stdio")
        elif transport == "sse":
            self.mcp.run(transport="sse")
        else:
            raise ValueError(f"Unknown transport: {transport}")


# Create selenium mcp instance
selenium_server = SeleniumMCPServer()

# Expose the MCP instance as a top-level variable with expected name
mcp = selenium_server.mcp


# Create and run the selenium_server
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Give a model the ability to control a browser through Selenium"
    )
    parser.add_argument(
        "--advanced-tools", action="store_true", help="Enable selenium advanced tools"
    )
    parser.add_argument(
        "--undetected-bot",
        action="store_true",
        help="Attempt to hide that selenium is a bot to webpages",
    )
    parser.add_argument(
        "--transport",
        choices=["sse", "stdio"],
        default="stdio",
        help="Choose transport method: 'sse' or 'stdio' (default: stdio)",
    )
    args = parser.parse_args()

    try:
        selenium_server.run(
            transport=args.transport,
            advanced_tools=args.advanced_tools,
            undetected_bot=args.undetected_bot,
        )
    finally:
        selenium_server.quit_browser()
