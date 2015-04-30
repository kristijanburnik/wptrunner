import httplib
import json
import socket
import time
import urlparse
from collections import defaultdict

class WebDriverException(Exception):
    http_status = None
    status_code = None
    def __init__(self, message):
        self.message = message

class ElementNotSelectableException(WebDriverException):
    http_status = 400
    status_code = "element not selectable"

class ElementNotVisibleException(WebDriverException):
    http_status = 400
    status_code = "element not visible"

class InvalidArgumentException(WebDriverException):
    http_status = 400
    status_code = "invalid argument"

class InvalidCookieDomainException(WebDriverException):
    http_status = 400
    status_code = "invalid cookie domain"

class InvalidElementCoordinatesException(WebDriverException):
    http_status = 400
    status_code = "invalid element coordinates"

class InvalidElementStateException(WebDriverException):
    http_status = 400
    status_code = "invalid cookie domain"

class InvalidSelectorException(WebDriverException):
    http_status = 400
    status_code = "invalid selector"

class InvalidSessionIdException(WebDriverException):
    http_status = 404
    status_code = "invalid session id"

class JavascriptErrorException(WebDriverException):
    http_status = 500
    status_code = "javascript error"

class MoveTargetOutOfBoundsException(WebDriverException):
    http_status = 500
    status_code = "move target out of bounds"

class NoSuchAlertException(WebDriverException):
    http_status = 400
    status_code = "no such alert"

class NoSuchElementException(WebDriverException):
    http_status = 404
    status_code = "no such element"

class NoSuchFrameException(WebDriverException):
    http_status = 400
    status_code = "no such frame"

class NoSuchWindowException(WebDriverException):
    http_status = 400
    status_code = "no such window"

class ScriptTimeoutException(WebDriverException):
    http_status = 408
    status_code = "script timeout"

class SessionNotCreatedException(WebDriverException):
    http_status = 500
    status_code = "session not created"

class StaleElementReferenceException(WebDriverException):
    http_status = 400
    status_code = "stale element reference"

class TimeoutException(WebDriverException):
    http_status = 408
    status_code = "timeout"

class UnableToSetCookieException(WebDriverException):
    http_status = 500
    status_code = "unable to set cookie"

class UnexpectedAlertOpenException(WebDriverException):
    http_status = 500
    status_code = "unexpected alert open"

class UnknownErrorException(WebDriverException):
    http_status = 500
    status_code = "unknown error"

class UnknownCommandException(WebDriverException):
    http_status = (404, 405)
    status_code = "unknown command"

class UnsupportedOperationException(WebDriverException):
    http_status = 500
    status_code = "unsupported operation"

_objs = locals().values()

def group_exceptions():
    exceptions = defaultdict(dict)
    for item in _objs:
        if type(item) == type and issubclass(item, WebDriverException):
            if not isinstance(item.http_status, tuple):
                statuses = (item.http_status,)
            else:
                statuses = item.http_status

            for status in statuses:
                exceptions[status][item.status_code] = item
    return exceptions

_exceptions = group_exceptions()
del _objs
del group_exceptions

def wait_for_port(host, port, timeout=60):
    """ Wait for the specified Marionette host/port to be available."""
    starttime = time.time()
    poll_interval = 0.1
    while time.time() - starttime < timeout:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((host, port))
            return True
        except socket.error:
            pass
        finally:
            if sock:
                sock.close()
        time.sleep(poll_interval)
    return False

class Transport(object):
    def __init__(self, host, port, url_prefix="", port_timeout=60):
        self.host = host
        self.port = port
        self.port_timeout = port_timeout
        if url_prefix == "":
            self.path_prefix = "/"
        else:
            self.path_prefix = "/%s/" % url_prefix.strip("/")
        self._connection = None

    def connect(self):
        wait_for_port(self.host, self.port, self.port_timeout)
        self._connection = httplib.HTTPConnection(self.host, self.port)

    def close_connection(self):
        if self._connection:
            self._connection.close()
        self._connection = None

    def url(self, suffix):
        return urlparse.urljoin(self.url_prefix, suffix)

    def send(self, method, url, body=None, headers=None, key=None):
        if not self._connection:
            self.connect()

        if body is None and method == "POST":
            body = {}

        if isinstance(body, dict):
            body = json.dumps(body)

        if isinstance(body, unicode):
            body = body.encode("utf-8")

        if headers is None:
            headers = {}

        url = self.path_prefix + url

        self._connection.request(method, url, body, headers)

        try:
            resp = self._connection.getresponse()
        except Exception:
            # This should probably be more specific
            raise IOError
        body = resp.read()


        try:
            data = json.loads(body)
        except:
            raise
            raise WebDriverException("Could not parse response body as JSON: %s" % body)

        if resp.status != 200:
            print resp.status, data
            print _exceptions.get(resp.status, {})
            print _exceptions.get(resp.status, {}).get(data.get("status", None), WebDriverException)
            cls = _exceptions.get(resp.status, {}).get(data.get("status", None), WebDriverException)
            raise cls(data.get("message", "No error message given"))

        if key is not None:
            data = data[key]

        if not data:
            data = None

        return data

def command(func):
    def inner(self, *args, **kwargs):
        if self.session_id is None:
            raise SessionNotCreatedException("Session not created")
        return func(self, *args, **kwargs)

    inner.__name__ = func.__name__
    inner.__doc__ = func.__doc__

    return inner

class Session(object):
    def __init__(self, host, port, url_prefix="", desired_capabilities=None, port_timeout=60):
        self.transport = Transport(host, port, url_prefix, port_timeout)
        self.desired_capabilities = desired_capabilities
        self.session_id = None

    def start(self):
        desired_capabilities = self.desired_capabilities if self.desired_capabilities else {}
        body = {"capabilities": {"desiredCapabilites": desired_capabilities}}

        rv = self.transport.send("POST", "session")
        self.session_id = rv["sessionId"]

        return rv["value"]

    @command
    def end(self):
        url = "session/%s" % self.session_id
        self.trasnport.send("DELETE", url)
        self.session_id = None
        self.transport.close_connection()

    def __enter__(self):
        resp = self.start()
        if resp.error:
            raise Exception(resp)
        return self

    def __exit__(self, *args, **kwargs):
        resp = self.end()
        if resp.error:
            raise Exception(resp)

    def send_command(self, method, url, body=None, key=None):
        url = urlparse.urljoin("session/%s/" % self.session_id, url)
        return self.transport.send(method, url, body, key=key)

    @command
    def get(self, url):
        if urlparse.urlsplit(url).netloc is None:
            return self.url(url)
        body = {"url": url}
        return self.send_command("POST", "url", body)

    @property
    @command
    def current_url(self):
        return self.send_command("GET", "url", key="value")

    @command
    def go_back(self):
        return self.send_command("POST", "back")

    @command
    def go_forward(self):
        return self.send_command("POST", "forward")

    @command
    def refresh(self):
        return self.send_command("POST", "refresh")

    @property
    @command
    def title(self):
        return self.send_command("GET", "title", key="value")

    @property
    @command
    def window_handle(self):
        return self.send_command("GET", "window_handle", key="value")

    @property
    @command
    def window_handles(self):
        return self.send_command("GET", "window_handles", key="value")

    @command
    def close(self):
        return self.send_command("DELETE", "window_handle")

    @command
    def set_window_size(self, height, width):
        body = {"width": width,
                "height": height}

        return self.send_command("POST", "window/size", body)

    @property
    @command
    def window_size(self):
        return self.send_command("GET", "window/size")

    @property
    @command
    def maximize_window(self):
        return self.send_command("POST", "window/maximize")

    @command
    def switch_to_window(self, handle):
        body = {"handle": handle}
        return self.send_command("POST", "window")

    # TODO: not properly defined
    # def fullscreen_window(self, raw_body=Missing, headers=Missing):
    #     return self.send_command("POST", "", raw_body, headers)

    #[...]

    @command
    def find_element(self, strategy, selector):
        body = {"using": strategy,
                "value": selector}

        element_id = self.send_command("POST", "element", body, key="value")

        try:
            elem = self.element(resp.data["value"])
        except Exception as e:
            elem = None

        return elem

    def element(self, data):
        return Element(self, data["element-6066-11e4-a52e-4f735466cecf"])


    #[...]

    @command
    def execute_script(self, script, args=None):
        if args is None:
            args = []

        body = {
            "script": script,
            "args": args
        }
        return self.send_command("POST", "execute", body, key="value")

    @command
    def execute_async_script(self, script, args=None):
        if args is None:
            args = []

        body = {
            "script": script,
            "args": args
        }
        return self.send_command("POST", "execute_async", body, key="value")

    #[...]

    @command
    def screenshot(self):
        return self.send_command("GET", "screenshot", key="value")

class Element(object):
    def __init__(self, session, id):
        self.session = session
        self.id = id

    @property
    def session_id(self):
        return self.session.session_id

    def url(self, suffix):
        return "element/%s/%s" % (self.id, suffix)

    @command
    def find_element(self, strategy, selector):
        body = {"using": strategy,
                "value": selector}

        elem = self.session.send_command("POST", self.url("element"), body, key="value")
        return self.session.element(elem)

    @command
    def send_keys(self, keys):
        if isinstance(keys, (str, unicode)):
            keys = [char for char in keys]

        body = {"value": keys}

        return self.session.send_command("POST", self.url("value"), body)
