# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os
import socket
import sys
import threading
import time
import traceback
import urlparse
import uuid

from .base import (ExecutorException,
                   Protocol,
                   RefTestExecutor,
                   RefTestImplementation,
                   TestExecutor,
                   TestharnessExecutor,
                   testharness_result_converter,
                   reftest_result_converter,
                   strip_server)
import webdriver
from ..testrunner import Stop

here = os.path.join(os.path.split(__file__)[0])

extra_timeout = 5

class ServoWebDriverProtocol(Protocol):
    def __init__(self, executor, browser, capabilities, **kwargs):
        Protocol.__init__(self, executor, browser)
        self.capabilities = capabilities
        self.host = browser.webdriver_host
        self.port = browser.webdriver_port
        self.session = None

    def setup(self, runner):
        """Connect to browser via WebDriver."""
        self.runner = runner

        session_started = False
        try:
            self.session = webdriver.Session(self.host, self.port)
            self.session.start()
        except:
            self.logger.warning(
                "Connecting with WebDriver failed:\n%s" % traceback.format_exc())
        else:
            self.logger.debug("session started")
            session_started = True

        if not session_started:
            self.logger.warning("Failed to connect via WebDriver")
            self.executor.runner.send_message("init_failed")
        else:
            self.executor.runner.send_message("init_succeeded")

    def teardown(self):
        self.logger.debug("Hanging up on WebDriver session")
        try:
            self.session.end()
        except:
            pass

    def is_alive(self):
        try:
            # Get a simple property over the connection
            self.session.window_handle
        # TODO what exception?
        except (socket.timeout, webdriver.TimeoutException, IOError):
            return False
        return True

    def after_connect(self):
        pass

    def wait(self):
        # This is very stupid
        while True:
            if not self.is_alive():
                break
            time.sleep(1)

def timeout_func(timeout):
    if timeout:
        t0 = time.time()
        return lambda: time.time() - t0 > timeout + extra_timeout
    else:
        return lambda: False

class ServoWebDriverTestharnessExecutor(TestharnessExecutor):
    def __init__(self, browser, server_config, timeout_multiplier=1,
                 close_after_done=True, capabilities=None, debug_info=None):
        TestharnessExecutor.__init__(self, browser, server_config, timeout_multiplier=1,
                                     debug_info=None)
        self.protocol = ServoWebDriverProtocol(self, browser, capabilities=capabilities)
        self.script = None

    def on_protocol_change(self, new_protocol):
        pass

    def do_test(self, test):
        url = self.test_url(test)
        session = self.protocol.session
        timeout = test.timeout * self.timeout_multiplier if self.debug_info is None else None

        timed_out = timeout_func(timeout)

        try:
            # Without this pause I get a panic in the webdriver server
            session.get(url)
            while not timed_out():
                data = session.execute_script("""
    var elem = document.getElementById('__testharness__results__');
    if (elem === null) {
       return null;
    } else {
       return elem.textContent;
    }""")
                if data is not None:
                    break
                time.sleep(0.1)
        except IOError:
            return test.result_cls("CRASH", None), []
        except Exception as e:
            message = getattr(e, "message", ""), []
            if message:
                message += "\n"
            message += traceback.format_exc(e)
            return test.result_cls("ERROR", message), []

        if data is None:
            return test.result_cls("TIMEOUT", None), []

        result_data = json.loads(data)
        result_data["test"] = test.url

        return self.convert_result(test, result_data)

    def is_alive(self):
        return self.protocol.is_alive()

class TimeoutError(Exception):
    pass


class ServoWebDriverRefTestExecutor(RefTestExecutor):
    def __init__(self, browser, server_config, timeout_multiplier=1,
                 screenshot_cache=None, capabilities=None, debug_info=None):
        """Selenium WebDriver-based executor for reftests"""
        RefTestExecutor.__init__(self,
                                 browser,
                                 server_config,
                                 screenshot_cache=screenshot_cache,
                                 timeout_multiplier=timeout_multiplier,
                                 debug_info=debug_info)
        self.protocol = ServoWebDriverProtocol(self, browser,
                                               capabilities=capabilities)
        self.implementation = RefTestImplementation(self)

    def is_alive(self):
        return self.protocol.is_alive()

    def do_test(self, test):
        try:
            result = self.implementation.run_test(test)
            return self.convert_result(test, result)
        except IOError:
            return test.result_cls("CRASH", None), []
        except TimeoutError:
            return test.result_cls("TIMEOUT", None), []
        except Exception as e:
            message = getattr(e, "message", "")
            if message:
                message += "\n"
            message += traceback.format_exc(e)
            return test.result_cls("ERROR", message), []

    def screenshot(self, test):
        url = self.test_url(test)
        session = self.protocol.session

        timeout = test.timeout * self.timeout_multiplier if self.debug_info is None else None

        timed_out = timeout_func(timeout)

        session.get(url)
        while not timed_out():
            ready = session.execute_script("""return (document.readyState === 'complete' && Array.prototype.indexOf.call(document.body.classList, 'reftest-wait') === -1)""")
            if ready:
                self.logger.debug("Taking screenshot of %s" % url)
                return True, session.screenshot()
            time.sleep(0.1)

        raise False, ("TIMEOUT", None)
