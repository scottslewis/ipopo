#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the MQTT service

:author: Thomas Calmant
"""

# Standard library
import random
import shutil
import string
import tempfile
import time
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# Pelix
import pelix.framework
import pelix.services as services

from tests.mqtt_utilities import find_mqtt_server

# ------------------------------------------------------------------------------

__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class Listener:
    """
    Sample listener
    """
    def __init__(self):
        """
        Sets up members
        """
        self.messages = []

    def handle_mqtt_message(self, topic, payload, qos):
        """
        Got a message
        """
        self.messages.append((topic, payload, qos))


class MqttServiceTest(unittest.TestCase):
    """
    Tests the MQTT utility service
    """
    HOST = find_mqtt_server()
    PORT = 1883

    def setUp(self):
        """
        Prepares a framework and a registers a service to export
        """
        # Prepare a temporary configuration folder
        self.conf_dir = tempfile.mkdtemp()

        # Create the framework
        # The MQTT component is automatically started
        self.framework = pelix.framework.create_framework(
            ('pelix.ipopo.core',
             'pelix.services.configadmin',
             'pelix.services.mqtt'),
            {'configuration.folder': self.conf_dir})
        self.framework.start()

        # Get the configuration admin service
        context = self.framework.get_bundle_context()
        self.config_ref = context.get_service_reference(
            services.SERVICE_CONFIGURATION_ADMIN)
        self.config = context.get_service(self.config_ref)

    def tearDown(self):
        """
        Cleans up for next test
        """
        # Stop the framework
        pelix.framework.FrameworkFactory.delete_framework(self.framework)
        self.framework = None

        # Clean up
        shutil.rmtree(self.conf_dir)

    def test_no_config(self):
        """
        Tests MQTT utility without configuration
        """
        # Wait a bit
        time.sleep(.5)

        # Check if a service is active
        context = self.framework.get_bundle_context()
        svc_ref = context.get_service_reference(
            services.SERVICE_MQTT_CONNECTION)
        self.assertIsNone(svc_ref, "Found a MQTT connection")

    def _setup_mqtt(self, context):
        """
        Common code for MQTT service creation
        """
        # Setup MQTT connection
        config = self.config.create_factory_configuration(
            services.MQTT_CONNECTOR_FACTORY_PID)
        config.update({"host": self.HOST, "port": self.PORT})

        # Wait for service
        for _ in range(10):
            svc_ref = context.get_service_reference(
                services.SERVICE_MQTT_CONNECTION,
                "(id={})".format(config.get_pid()))
            if svc_ref is not None:
                break
            time.sleep(.5)
        else:
            self.fail("Connection Service not found")
        return config, svc_ref

    def test_configuration(self):
        """
        Tests service configuration
        """
        # Prepare service
        context = self.framework.get_bundle_context()
        config, svc_ref = self._setup_mqtt(context)

        # Assert we have the same PID
        props = svc_ref.get_properties()
        self.assertEqual(props['host'], self.HOST)
        self.assertEqual(props['port'], self.PORT)
        self.assertEqual(props['id'], config.get_pid())

        # Delete configuration
        config.delete()

        # Wait for service to be unregistered
        context = self.framework.get_bundle_context()
        for _ in range(10):
            svc_ref = context.get_service_reference(
                services.SERVICE_MQTT_CONNECTION,
                "(id={})".format(config.get_pid()))
            if svc_ref is None:
                break
            time.sleep(.5)
        else:
            self.fail("Connection Service still there")

    def __send_message(self, client, topic, qos):
        """
        Sends a message using the given client (content is generated)

        :param client: MQTT client
        :param topic: Message topic
        :param qos: Requested quality of service
        :return: Payload of the message
        """
        payload = list(string.ascii_letters)
        random.shuffle(payload)
        payload = ''.join(payload).encode("utf-8")
        client.publish(topic, payload, qos=qos)
        return payload

    def test_messages(self):
        """
        Tests messages publication and reception
        """
        # Prepare service 1
        context = self.framework.get_bundle_context()
        config, svc_ref = self._setup_mqtt(context)
        mqtt_1 = context.get_service(svc_ref)

        # Prepare service 2
        config_2, svc_ref = self._setup_mqtt(context)
        mqtt_2 = context.get_service(svc_ref)

        # Assert that we have two different services
        self.assertIsNot(mqtt_1, mqtt_2, "Same services returned")

        # Register a publisher
        listener = Listener()
        lst_reg = context.register_service(
            services.SERVICE_MQTT_LISTENER, listener,
            {services.PROP_MQTT_TOPICS: "/pelix/test/#"})

        # Check the initial test condition
        self.assertListEqual(listener.messages, [], "Invalid precondition")

        # Send a message
        topic = "/pelix/test/foobar"
        payload = self.__send_message(mqtt_1, topic, 1)

        # Wait for it
        for _ in range(10):
            try:
                msg_topic, msg_payload, qos = listener.messages.pop()
                break
            except IndexError:
                time.sleep(.5)
        else:
            self.fail("Got no message")

        # Check message
        self.assertEqual(msg_topic, topic)
        self.assertEqual(msg_payload, payload)

        # Test with a filtered out topic
        topic = "/pelix/foo/bar"
        self.__send_message(mqtt_1, topic, 1)

        # Wait for something
        for _ in range(6):
            try:
                msg_topic, msg_payload, qos = listener.messages.pop()
            except IndexError:
                time.sleep(.5)
            else:
                # It is possible we got a copy of the previous message
                # (QOS 1: at least one time)
                if msg_topic == topic:
                    self.fail("Got a message that should be filtered: {}"
                              .format(msg_topic))

        # Change topic filter
        lst_reg.set_properties({services.PROP_MQTT_TOPICS: "/pelix/foo/#"})
        payload = self.__send_message(mqtt_1, topic, 1)

        # Wait for it
        for _ in range(10):
            try:
                msg_topic, msg_payload, qos = listener.messages.pop()
                break
            except IndexError:
                time.sleep(.5)
        else:
            self.fail("Got no message")

        # Check message
        self.assertEqual(msg_topic, topic)
        self.assertEqual(msg_payload, payload)

        # Unregister service
        lst_reg.unregister()

        # Clean up
        del listener.messages[:]

        # Send a message
        self.__send_message(mqtt_1, topic, 1)

        # Wait for something
        for _ in range(6):
            try:
                listener.messages.pop()
            except IndexError:
                time.sleep(.5)
            else:
                self.fail("Got an unexpected message")

        # Clean up
        config.delete()
        config_2.delete()
