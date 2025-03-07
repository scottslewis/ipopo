#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
iPOPO installation script

:author: Thomas Calmant
:copyright: Copyright 2024, Thomas Calmant
:license: Apache License 2.0
:version: 3.0.0

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

import os

from setuptools import setup

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 0, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


def read(fname):
    """
    Utility method to read the content of a whole file
    """
    with open(os.path.join(os.path.dirname(__file__), fname)) as fd:
        return fd.read()


setup(
    name="iPOPO",
    version=__version__,
    license="Apache License 2.0",
    license_file="LICENSE",
    description="A service-oriented component model framework",
    long_description=read("README.rst"),
    author="Thomas Calmant",
    author_email="thomas.calmant@gmail.com",
    url="https://github.com/tcalmant/ipopo/",
    packages=[
        "pelix",
        "pelix.http",
        "pelix.internals",
        "pelix.ipopo",
        "pelix.ipopo.handlers",
        "pelix.misc",
        "pelix.remote",
        "pelix.remote.discovery",
        "pelix.remote.transport",
        "pelix.rsa",
        "pelix.rsa.providers",
        "pelix.rsa.providers.discovery",
        "pelix.rsa.providers.distribution",
        "pelix.rsa.topologymanagers",
        "pelix.services",
        "pelix.shell",
        "pelix.shell.completion",
    ],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
    ],
    install_requires=["jsonrpclib-pelix>=0.4.3"],
    extras_require={
        "Redis": ["redis>=2.10"],
        "ZooKeeper": ["kazoo==2.8.0"],
        "MQTT": ["paho-mqtt>=2.1"],
        "XMPP": ["slixmpp>=1.8.4"],
        "zeroconf": ["zeroconf==0.19"],
        "RSA": ["etcd3>=0.12.0", "osgiservicebridge>=1.5.1"],
    },
)
