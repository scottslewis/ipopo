#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Defines the decorators associated shell completion handlers to a shell function

:author: Thomas Calmant
:copyright: Copyright 2023, Thomas Calmant
:license: Apache License 2.0
:version: 1.0.2
:status: Alpha

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

from typing import List

from . import ATTR_COMPLETERS, CompletionInfo

try:
    # Everything here relies on readline
    import readline
except ImportError:
    readline = None

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"


# ------------------------------------------------------------------------------

DUMMY = "dummy"
""" Completer ID: a completer that does nothing """

BUNDLE = "pelix.bundle"
""" Completer ID: Pelix Bundle ID completer """

SERVICE = "pelix.service"
""" Completer ID: Pelix Service ID completer """

FACTORY = "ipopo.factory"
""" Completer ID: iPOPO Factory Name completer """

FACTORY_PROPERTY = "ipopo.factory.property"
""" Completer ID: iPOPO Property Name completer """

COMPONENT = "ipopo.component"
""" Completer ID: iPOPO Component Name completer """

# ------------------------------------------------------------------------------


class Completion:
    """
    Decorator that sets up the arguments completion of a shell method
    """

    def __init__(self, *completers: str, **kwargs: bool) -> None:
        """
        :param completers: A list of IDs (str) of argument completers
        :param multiple: If True, the last completer is reused multiple times
        """
        self._completers: List[str] = list(completers)
        self._multiple = kwargs.get("multiple", False)

    def __call__(self, method):
        """
        Adds a CoreCompleter with the list of completers as metadata of the
        method.
        Does nothing if the readline library isn't available

        :param method: Decorated method
        :return: The method with a new metadata for the Pelix Shell
        """
        if readline is not None and self._completers:
            # No need to setup completion if readline isn't available
            setattr(
                method,
                ATTR_COMPLETERS,
                CompletionInfo(self._completers, self._multiple),
            )

        return method
