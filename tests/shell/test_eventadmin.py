#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the EventAdmin shell commands

:author: Thomas Calmant
"""

import threading
from typing import Any, Dict, List, Optional, Tuple, Union
import unittest

import pelix.framework
from pelix.internals.registry import ServiceRegistration
import pelix.services
import pelix.shell
from pelix.ipopo.constants import use_ipopo

# ------------------------------------------------------------------------------

__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class DummyEventHandler(pelix.services.ServiceEventHandler):
    """
    Dummy event handler
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        # Topic of the last received event
        self.last_event: Optional[str] = None
        self.last_props: Dict[str, Any] = {}
        self.__event = threading.Event()

    def handle_event(self, topic: str, properties: Dict[str, Any]) -> None:
        """
        Handles an event received from EventAdmin
        """
        # Keep received values
        self.last_event = topic
        self.last_props = properties
        self.__event.set()

    def pop_event(self) -> Optional[str]:
        """
        Pops the list of events
        """
        # Clear the event for next try
        self.__event.clear()

        # Reset last event
        event, self.last_event = self.last_event, None
        return event

    def wait(self, timeout: float) -> None:
        """
        Waits for the event to be received
        """
        self.__event.wait(timeout)


# ------------------------------------------------------------------------------


class EventAdminShellTest(unittest.TestCase):

    """
    Tests the EventAdmin shell commands
    """

    framework: pelix.framework.Framework
    eventadmin: pelix.services.EventAdmin
    shell: pelix.shell.ShellService

    def setUp(self) -> None:
        """
        Prepares a framework and a registers a service to export
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(
            ("pelix.ipopo.core", "pelix.shell.core", "pelix.services.eventadmin", "pelix.shell.eventadmin")
        )
        self.framework.start()

        # Get the Shell service
        context = self.framework.get_bundle_context()
        svc_ref = context.get_service_reference(pelix.shell.ShellService)
        assert svc_ref is not None
        self.shell = context.get_service(svc_ref)

        # Instantiate the EventAdmin component
        context = self.framework.get_bundle_context()
        with use_ipopo(context) as ipopo:
            self.eventadmin = ipopo.instantiate(pelix.services.FACTORY_EVENT_ADMIN, "evtadmin", {})

    def _register_handler(
        self, topics: Union[None, str, List[str]], evt_filter: Optional[str] = None
    ) -> Tuple[DummyEventHandler, ServiceRegistration[pelix.services.ServiceEventHandler]]:
        """
        Registers an event handler

        :param topics: Event topics
        :param evt_filter: Event filter
        """
        svc = DummyEventHandler()
        context = self.framework.get_bundle_context()
        svc_reg = context.register_service(
            pelix.services.ServiceEventHandler,
            svc,
            {pelix.services.PROP_EVENT_TOPICS: topics, pelix.services.PROP_EVENT_FILTER: evt_filter},
        )
        return svc, svc_reg

    def _run_command(self, command: str, *args: Any) -> None:
        """
        Runs the given shell command
        """
        # Format command
        if args:
            command = command.format(*args)

        # Run command
        self.shell.execute(command)

    def tearDown(self) -> None:
        """
        Cleans up for next test
        """
        # Stop the framework
        pelix.framework.FrameworkFactory.delete_framework(self.framework)
        self.framework = None  # type: ignore

    def testTopics(self) -> None:
        """
        Tests sending topics
        """
        # Prepare a handler
        handler, _ = self._register_handler("/titi/*")

        # Send events, with a matching topic
        for topic in ("/titi/toto", "/titi/", "/titi/42", "/titi/toto/tata"):
            self._run_command("send {0}", topic)
            self.assertEqual(handler.pop_event(), topic)

        # Send events, with a non-matching topic
        for topic in ("/toto/titi/42", "/titi", "/toto/42"):
            self._run_command("send {0}", topic)
            self.assertEqual(handler.pop_event(), None)

    def testFilters(self) -> None:
        """
        Tests the sending events with properties
        """
        # Prepare a handler
        key = "some.key"
        handler, _ = self._register_handler(None, f"({key}=42)")

        # Assert the handler is empty
        self.assertEqual(handler.pop_event(), None)

        # Send event, with matching properties
        for topic in ("/titi/toto", "/toto/", "/titi/42", "/titi/toto/tata"):
            value = 42
            evt_props = {key: value}
            self._run_command("send {0} {1}=42", topic, key, value)

            # Check properties
            self.assertIn(key, handler.last_props)
            self.assertEqual(str(handler.last_props[key]), str(value))
            self.assertIsNot(handler.last_props, evt_props)

            # Check topic
            self.assertEqual(handler.pop_event(), topic)

            # Send events, with a non-matching properties
            self._run_command("send {0} {1}=21", topic, key)
            self.assertEqual(handler.pop_event(), None)

    def testPost(self) -> None:
        """
        Tests the post event method
        """
        # Prepare a handler
        handler, _ = self._register_handler("/titi/*")

        # Post a message
        topic = "/titi/toto"
        self._run_command("post {0}", topic)

        # Wait a little
        handler.wait(1)
        self.assertEqual(handler.pop_event(), topic)
