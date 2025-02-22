#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Runs the framework corresponding to the iPOPO Remote Services server.

Usage: run_remote.py [-h] [-s] [-p HTTP_PORT] [-d [DISCOVERY [DISCOVERY ...]]]
                     [-t [TRANSPORT [TRANSPORT ...]]]

* -s: Run in "provider mode", the framework provides a remote service. If not
  given, the framework will consume the remote services it finds

* -p: Force the HTTP server port (default: use a random one)

* -d: Select the discovery protocol(s) to use (default: multicast)
  Available protocols: multicast, mdns

* -t: Select the transport protocol(s) to use (default: jsonrpc)
  Available protocols: jsonrpc, jabsorbrpc

:author: Thomas Calmant
:copyright: Copyright 2023, Thomas Calmant
:license: Apache License 2.0
:version: 1.0.2

..

    Copyright 2023 Thomas Calmant

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

import argparse
import logging
import sys
from typing import Any

import pelix.constants
import pelix.framework
import pelix.remote as rs
from pelix.ipopo.constants import use_waiting_list

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Available discovery protocols
DISCOVERIES = ("multicast", "mqtt", "mdns", "redis", "zookeeper")

# Available transport protocols
TRANSPORTS = ("xmlrpc", "jsonrpc", "mqttrpc", "jabsorbrpc")

# ------------------------------------------------------------------------------


class InstallUtils:
    """
    Utility class to install services and instantiate components in a framework
    """

    def __init__(self, context: pelix.framework.BundleContext, arguments: Any) -> None:
        """
        Sets up the utility class

        :param context: Bundle context
        :param arguments: Program arguments
        """
        self.context = context
        self.arguments = arguments

    def discovery_multicast(self) -> None:
        """
        Installs the multicast discovery bundles and instantiates components
        """
        # Install the bundle
        self.context.install_bundle("pelix.remote.discovery.multicast").start()

        with use_waiting_list(self.context) as ipopo:
            # Instantiate the discovery
            ipopo.add(rs.FACTORY_DISCOVERY_MULTICAST, "pelix-discovery-multicast")

    def discovery_mdns(self) -> None:
        """
        Installs the mDNS discovery bundles and instantiates components
        """
        # Remove Zeroconf debug output
        logging.getLogger("zeroconf").setLevel(logging.WARNING)

        # Install the bundle
        self.context.install_bundle("pelix.remote.discovery.mdns").start()

        with use_waiting_list(self.context) as ipopo:
            # Instantiate the discovery
            ipopo.add(rs.FACTORY_DISCOVERY_ZEROCONF, "pelix-discovery-zeroconf")

    def discovery_mqtt(self) -> None:
        """
        Installs the MQTT discovery bundles and instantiates components
        """
        # Install the bundle
        self.context.install_bundle("pelix.remote.discovery.mqtt").start()

        with use_waiting_list(self.context) as ipopo:
            # Instantiate the discovery
            ipopo.add(
                rs.FACTORY_DISCOVERY_MQTT,
                "pelix-discovery-mqtt",
                {
                    "application.id": "sample.rs",
                    "mqtt.host": self.arguments.mqtt_host,
                    "mqtt.port": self.arguments.mqtt_port,
                },
            )

    def discovery_redis(self) -> None:
        """
        Installs the Redis discovery bundles and instantiates components
        """
        # Install the bundle
        self.context.install_bundle("pelix.remote.discovery.redis").start()

        with use_waiting_list(self.context) as ipopo:
            # Instantiate the discovery
            ipopo.add(
                rs.FACTORY_DISCOVERY_REDIS,
                "pelix-discovery-redis",
                {
                    "application.id": "sample.rs",
                    "redis.host": self.arguments.redis_host,
                    "redis.port": self.arguments.redis_port,
                },
            )

    def discovery_zookeeper(self) -> None:
        """
        Installs the ZooKeeper discovery bundles and instantiates components
        """
        # Install the bundle
        self.context.install_bundle("pelix.remote.discovery.zookeeper").start()

        with use_waiting_list(self.context) as ipopo:
            # Instantiate the discovery
            ipopo.add(
                rs.FACTORY_DISCOVERY_ZOOKEEPER,
                "pelix-discovery-zookeeper",
                {
                    "application.id": "sample.rs",
                    "zookeeper.hosts": self.arguments.zk_hosts,
                    "zookeeper.prefix": self.arguments.zk_prefix,
                },
            )

    def transport_jsonrpc(self) -> None:
        """
        Installs the JSON-RPC transport bundles and instantiates components
        """
        # Install the bundle
        self.context.install_bundle("pelix.remote.json_rpc").start()

        with use_waiting_list(self.context) as ipopo:
            # Instantiate the discovery
            ipopo.add(rs.FACTORY_TRANSPORT_JSONRPC_EXPORTER, "pelix-jsonrpc-exporter")
            ipopo.add(rs.FACTORY_TRANSPORT_JSONRPC_IMPORTER, "pelix-jsonrpc-importer")

    def transport_jabsorbrpc(self) -> None:
        """
        Installs the JABSORB-RPC transport bundles and instantiates components
        """
        # Install the bundle
        self.context.install_bundle("pelix.remote.transport.jabsorb_rpc").start()

        with use_waiting_list(self.context) as ipopo:
            # Instantiate the discovery
            ipopo.add(
                rs.FACTORY_TRANSPORT_JABSORBRPC_EXPORTER,
                "pelix-jabsorbrpc-exporter",
            )
            ipopo.add(
                rs.FACTORY_TRANSPORT_JABSORBRPC_IMPORTER,
                "pelix-jabsorbrpc-importer",
            )

    def transport_mqttrpc(self) -> None:
        """
        Installs the MQTT-RPC transport bundles and instantiates components
        """
        # Install the bundle
        self.context.install_bundle("pelix.remote.transport.mqtt_rpc").start()

        with use_waiting_list(self.context) as ipopo:
            # Instantiate the discovery
            ipopo.add(
                rs.FACTORY_TRANSPORT_MQTTRPC_EXPORTER,
                "pelix-mqttrpc-exporter",
                {
                    "mqtt.host": self.arguments.mqtt_host,
                    "mqtt.port": self.arguments.mqtt_port,
                },
            )
            ipopo.add(
                rs.FACTORY_TRANSPORT_MQTTRPC_IMPORTER,
                "pelix-mqttrpc-importer",
                {
                    "mqtt.host": self.arguments.mqtt_host,
                    "mqtt.port": self.arguments.mqtt_port,
                },
            )

    def transport_xmlrpc(self) -> None:
        """
        Installs the XML-RPC transport bundles and instantiates components
        """
        # Install the bundle
        self.context.install_bundle("pelix.remote.xml_rpc").start()

        with use_waiting_list(self.context) as ipopo:
            # Instantiate the discovery
            ipopo.add(rs.FACTORY_TRANSPORT_XMLRPC_EXPORTER, "pelix-xmlrpc-exporter")
            ipopo.add(rs.FACTORY_TRANSPORT_XMLRPC_IMPORTER, "pelix-xmlrpc-importer")


# ------------------------------------------------------------------------------


def main(is_server, discoveries, transports, http_port, other_arguments) -> None:
    """
    Runs the framework

    :param is_server: If True, starts the provider bundle, else the consumer one
    :param discoveries: List of discovery protocols
    :param transports: List of RPC protocols
    :param http_port: Port of the HTTP server
    :param other_arguments: Other arguments
    """
    # Create the framework
    framework = pelix.framework.create_framework(
        (
            "pelix.ipopo.core",
            "pelix.ipopo.waiting",
            # Shell
            "pelix.shell.core",
            "pelix.shell.ipopo",
            "pelix.shell.console",
            # HTTP Service
            "pelix.http.basic",
            # Remote Services (core)
            "pelix.remote.dispatcher",
            "pelix.remote.registry",
        ),
        # Framework properties
        {pelix.constants.FRAMEWORK_UID: other_arguments.fw_uid},
    )

    # Start everything
    framework.start()
    context = framework.get_bundle_context()

    # Instantiate components
    # Get the iPOPO service
    with use_waiting_list(context) as ipopo:
        # Instantiate remote service components
        # ... HTTP server
        ipopo.add(
            "pelix.http.service.basic.factory",
            "http-server",
            {"pelix.http.address": "0.0.0.0", "pelix.http.port": http_port},
        )

        # ... servlet giving access to the registry
        ipopo.add(rs.FACTORY_REGISTRY_SERVLET, "pelix-remote-dispatcher-servlet")

    # Prepare the utility object
    util = InstallUtils(context, other_arguments)

    # Install the discovery bundles
    for discovery in discoveries:
        getattr(util, f"discovery_{discovery}")()

    # Install the transport bundles
    for transport in transports:
        getattr(util, f"transport_{transport}")()

    # Start the service provider or consumer
    if is_server:
        # ... the provider
        context.install_bundle("remote.provider").start()

    else:
        # ... or the consumer
        context.install_bundle("remote.consumer").start()

    # Start the framework and wait for it to stop
    framework.wait_for_stop()


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Parse arguments
    parser = argparse.ArgumentParser(description="Pelix Remote Services sample")

    # Provider or consumer
    parser.add_argument(
        "-s",
        "--server",
        "--provider",
        action="store_true",
        dest="is_server",
        help="Runs the framework with a service provider",
    )

    # Discovery
    parser.add_argument(
        "-d",
        "--discovery",
        nargs="*",
        default=(DISCOVERIES[0],),
        choices=DISCOVERIES,
        dest="discoveries",
        metavar="DISCOVERY",
        help="Discovery protocols to use (one of {0})".format(", ".join(DISCOVERIES)),
    )

    # Transport
    parser.add_argument(
        "-t",
        "--transport",
        nargs="*",
        default=(TRANSPORTS[0],),
        choices=TRANSPORTS,
        dest="transports",
        metavar="TRANSPORT",
        help="Transport protocols to use (one of {0})".format(", ".join(TRANSPORTS)),
    )

    # Framework configuration
    group = parser.add_argument_group("Framework Configuration", "Configuration of the Pelix framework")
    # ... HTTP server
    group.add_argument(
        "-p",
        "--port",
        action="store",
        type=int,
        default=0,
        dest="http_port",
        help="Port of the framework HTTP server (can be 0)",
    )

    # ... Framework UID
    group.add_argument(
        "--uid",
        action="store",
        default=None,
        dest="fw_uid",
        help="Forces the framework UID",
    )

    # MQTT configuration
    group = parser.add_argument_group(
        "MQTT Configuration",
        "Configuration of the MQTT discovery and" " RPC components",
    )
    # ... server
    group.add_argument(
        "--mqtt-host",
        action="store",
        dest="mqtt_host",
        default="test.mosquitto.org",
        help="MQTT server host (default: test.mosquitto.org)",
    )

    # ... port
    group.add_argument(
        "--mqtt-port",
        action="store",
        dest="mqtt_port",
        type=int,
        default=1883,
        help="MQTT server port (default: 1883)",
    )

    # Redis configuration
    group = parser.add_argument_group("Redis Configuration", "Configuration of Redis discovery")
    # ... server
    group.add_argument(
        "--redis-host",
        dest="redis_host",
        default="localhost",
        help="Redis server host (default: localhost)",
    )

    # ... port
    group.add_argument(
        "--redis-port",
        dest="redis_port",
        default=6379,
        type=int,
        help="Redis server port (default: 6379)",
    )

    # ZooKeeper configuration
    group = parser.add_argument_group("ZooKeeper Configuration", "Configuration of ZooKeeper discovery")
    # ... server
    group.add_argument(
        "--zk-hosts",
        dest="zk_hosts",
        default="localhost:2181",
        help="List of ZooKeeper servers (localhost:2181)",
    )

    # ... port
    group.add_argument(
        "--zk-prefix",
        dest="zk_prefix",
        default="/pelix",
        help="Prefix for ZooKeeper paths (/pelix)",
    )

    # Parse arguments
    args = parser.parse_args(sys.argv[1:])

    # Configure the logging package
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("kazoo.client").setLevel(logging.INFO)

    # Run the sample
    main(args.is_server, args.discoveries, args.transports, args.http_port, args)
