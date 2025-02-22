#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
@RequiresVarFilter Dependency handler

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

import logging
import string
from typing import Any, List, Optional, Union

import pelix.ipopo.constants as ipopo_constants
import pelix.ipopo.handlers.constants as constants
import pelix.ipopo.handlers.requires as requires
import pelix.ldapfilter as ldapfilter
from pelix.constants import ActivatorProto, BundleActivator
from pelix.framework import BundleContext
from pelix.internals.registry import ServiceRegistration
from pelix.ipopo.contexts import ComponentContext, Requirement

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class _HandlerFactory(requires._HandlerFactory):
    """
    Factory service for service registration handlers
    """

    def get_handlers(self, component_context: ComponentContext, instance: Any) -> List[constants.Handler]:
        """
        Sets up service providers for the given component

        :param component_context: The ComponentContext bean
        :param instance: The component instance
        :return: The list of handlers associated to the given component
        """
        # Extract information from the context
        requirements = component_context.get_handler(ipopo_constants.HANDLER_REQUIRES_VARIABLE_FILTER)
        requires_filters = component_context.properties.get(ipopo_constants.IPOPO_REQUIRES_FILTERS, None)

        # Prepare requirements
        requirements = self._prepare_requirements(requirements, requires_filters)

        # Set up the runtime dependency handlers
        handlers: List[constants.Handler] = []
        for field, requirement in requirements.items():
            # Construct the handler
            if requirement.aggregate:
                handlers.append(AggregateDependency(component_context, field, requirement))
            else:
                handlers.append(SimpleDependency(component_context, field, requirement))

        return handlers


@BundleActivator
class Activator(ActivatorProto):
    """
    The bundle activator
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        self._registration: Optional[ServiceRegistration[constants.HandlerFactory]] = None

    def start(self, context: BundleContext) -> None:
        """
        Bundle started
        """
        # Set up properties
        properties = {constants.PROP_HANDLER_ID: ipopo_constants.HANDLER_REQUIRES_VARIABLE_FILTER}

        # Register the handler factory service
        self._registration = context.register_service(
            constants.HandlerFactory,
            _HandlerFactory(),
            properties,
        )

    def stop(self, _: BundleContext) -> None:
        """
        Bundle stopped
        """
        if self._registration is not None:
            # Unregister the service
            self._registration.unregister()
            self._registration = None


# ------------------------------------------------------------------------------


class _VariableFilterMixIn(requires._RuntimeDependency):
    """
    Dependency handler MixIn to support variable filters
    """

    requirement: Requirement

    def __init__(self, component_context: ComponentContext, requirement: Requirement) -> None:
        """
        Set up the MixIn
        """
        # Component context
        self._component_context = component_context

        # Copy the current filter as a string
        self._original_filter = str(requirement.filter)
        self.valid_filter = False

        # List the properties found in the filter
        self._keys = self._find_keys()

        try:
            # Set the initial value of the filter
            self.update_filter()
        except ValueError:
            # The filter couldn't be initialized (reason already logged)
            self.valid_filter = False

    def _find_keys(self) -> List[str]:
        """
        Looks for the property keys in the filter string

        :return: A list of property keys
        """
        formatter = string.Formatter()
        return [val[1] for val in formatter.parse(self._original_filter) if val[1]]

    def update_filter(self) -> bool:
        """
        Update the filter according to the new properties

        :return: True if the filter changed, else False
        :raise ValueError: The filter is invalid
        """
        # Consider the filter invalid
        self.valid_filter = False

        try:
            # Format the new filter
            filter_str = self._original_filter.format(**self._component_context.properties)
        except KeyError as ex:
            # An entry is missing: abandon
            logging.warning("Missing filter value: %s", ex)
            raise ValueError("Missing filter value")

        try:
            # Parse the new LDAP filter
            new_filter = ldapfilter.get_ldap_filter(filter_str)
        except (TypeError, ValueError) as ex:
            logging.warning("Error parsing filter: %s", ex)
            raise ValueError("Error parsing filter")

        # The filter is valid
        self.valid_filter = True

        # Compare to the "old" one
        if new_filter != self.requirement.filter:
            # Replace the requirement filter
            self.requirement.filter = new_filter
            return True

        # Same filter
        return False

    def on_property_change(self, name: str, old_value: Any, new_value: Any) -> None:
        # pylint: disable=W0613
        """
        A component property has been updated

        :param name: Name of the property
        :param old_value: Previous value of the property
        :param new_value: New value of the property
        """
        if name in self._keys:
            try:
                if self.update_filter():
                    # This is a key for the filter and the filter has changed
                    # => Force the handler to update its dependency
                    self._reset()
            except ValueError:
                # Invalid filter: clear all references, this will invalidate
                # the component
                for svc_ref in self.get_bindings():
                    self.on_service_departure(svc_ref)

    def _reset(self) -> None:
        """
        Called when the filter has been changed
        """
        with self._lock:
            # Start listening to services with the new filter
            self.stop()
            self.start()

            # Force bindings update
            assert self._ipopo_instance is not None
            self._ipopo_instance.update_bindings()

            for svc_ref in self.get_bindings():
                # Check if the current reference matches the filter
                if self.requirement.filter is not None and not self.requirement.filter.matches(
                    svc_ref.get_properties()
                ):
                    # Not the case: emulate a service departure
                    # The instance life cycle will be updated as well
                    self.on_service_departure(svc_ref)


class SimpleDependency(_VariableFilterMixIn, requires.SimpleDependency):
    """
    Manages a single dependency field
    """

    def __init__(self, component_context: ComponentContext, field: str, requirement: Requirement) -> None:
        """
        Sets up members
        """
        requires.SimpleDependency.__init__(self, field, requirement)
        _VariableFilterMixIn.__init__(self, component_context, requirement)

    def is_valid(self) -> bool:
        """
        Tests if the dependency is in a valid state
        """
        return self.valid_filter and requires.SimpleDependency.is_valid(self)

    def try_binding(self) -> None:
        """
        Searches for the required service if needed

        :raise BundleException: Invalid ServiceReference found
        """
        if self.valid_filter:
            # Look for a service only if the filter is valid
            requires.SimpleDependency.try_binding(self)


class AggregateDependency(_VariableFilterMixIn, requires.AggregateDependency):
    """
    Manages a single dependency field
    """

    def __init__(self, component_context: ComponentContext, field: str, requirement: Requirement) -> None:
        """
        Sets up members
        """
        requires.AggregateDependency.__init__(self, field, requirement)
        _VariableFilterMixIn.__init__(self, component_context, requirement)

    def is_valid(self) -> bool:
        """
        Tests if the dependency is in a valid state
        """
        return self.valid_filter and requires.AggregateDependency.is_valid(self)

    def try_binding(self) -> None:
        """
        Searches for the required service if needed

        :raise BundleException: Invalid ServiceReference found
        """
        if self.valid_filter:
            # Look for a service only if the filter is valid
            requires.AggregateDependency.try_binding(self)
