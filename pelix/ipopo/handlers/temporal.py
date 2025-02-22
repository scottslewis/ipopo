#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Temporal dependency handler

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

import threading
from typing import Any, Callable, Dict, Generic, Iterable, Optional, Tuple, TypeVar, cast
from pelix.framework import BundleContext

import pelix.ipopo.constants as ipopo_constants
import pelix.ipopo.handlers.constants as constants
import pelix.ipopo.handlers.requires as requires
import pelix.utilities as utilities
from pelix.constants import ActivatorProto, BundleActivator
from pelix.internals.registry import ServiceReference, ServiceRegistration
from pelix.ipopo.contexts import ComponentContext, Requirement

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

T = TypeVar("T")

# ------------------------------------------------------------------------------


class _HandlerFactory(constants.HandlerFactory):
    """
    Factory service for service registration handlers
    """

    @staticmethod
    def _prepare_configs(
        configs: Dict[str, Any], requires_filters: Dict[str, str], temporal_timeouts: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Overrides the filters specified in the decorator with the given ones

        :param configs: Field → (Requirement, key, allow_none) dictionary
        :param requires_filters: Content of the 'requires.filter' component property (field → string)
        :param temporal_timeouts: Content of the 'temporal.timeouts' component property (field → float)
        :return: The new configuration dictionary
        """
        if not isinstance(requires_filters, dict):
            requires_filters = {}

        if not isinstance(temporal_timeouts, dict):
            temporal_timeouts = {}

        if not requires_filters and not temporal_timeouts:
            # No explicit configuration given
            return configs

        # We need to change a part of the requirements
        new_configs: Dict[str, Any] = {}
        for field, config in configs.items():
            # Extract values from tuple
            requirement, timeout = config
            explicit_filter = requires_filters.get(field)
            explicit_timeout = temporal_timeouts.get(field, timeout)

            # Convert the timeout value
            try:
                explicit_timeout = int(explicit_timeout)
                if explicit_timeout <= 0:
                    explicit_timeout = timeout
            except (ValueError, TypeError):
                explicit_timeout = timeout

            if not explicit_filter and not explicit_timeout:
                # Nothing to do
                new_configs[field] = config
            else:
                try:
                    # Store an updated copy of the requirement
                    requirement_copy = requirement.copy()
                    if explicit_filter:
                        requirement_copy.set_filter(explicit_filter)
                    new_configs[field] = (requirement_copy, explicit_timeout)
                except (TypeError, ValueError):
                    # No information for this one, or invalid filter:
                    # keep the factory requirement
                    new_configs[field] = config

        return new_configs

    def get_handlers(self, component_context: ComponentContext, instance: Any) -> Iterable[constants.Handler]:
        """
        Sets up service providers for the given component

        :param component_context: The ComponentContext bean
        :param instance: The component instance
        :return: The list of handlers associated to the given component
        """
        # Extract information from the context
        configs = component_context.get_handler(ipopo_constants.HANDLER_TEMPORAL)
        requires_filters = component_context.properties.get(ipopo_constants.IPOPO_REQUIRES_FILTERS, None)
        temporal_timeouts = component_context.properties.get(ipopo_constants.IPOPO_TEMPORAL_TIMEOUTS, None)

        # Prepare requirements
        new_configs = self._prepare_configs(configs, requires_filters, temporal_timeouts)

        # Return handlers
        return [
            TemporalDependency(field, requirement, timeout)
            for field, (requirement, timeout) in new_configs.items()
        ]


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
        properties = {constants.PROP_HANDLER_ID: ipopo_constants.HANDLER_TEMPORAL}

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


class TemporalException(constants.HandlerException):
    """
    Temporal exception
    """

    ...


class _TemporalProxy(Generic[T]):
    """
    The injected proxy
    """

    def __init__(self, timeout: float) -> None:
        """
        The temporal proxy
        """
        self.__event = utilities.EventData[T]()
        self.__timeout = timeout

    def set_service(self, service: T) -> None:
        """
        Sets the injected service

        :param service: The injected service, or None
        """
        self.__event.set(service)

    def unset_service(self) -> None:
        """
        The injected service has gone away
        """
        self.__event.clear()

    def __getattr__(self, item: str) -> Any:
        """
        Returns the attribute from the "real" service

        :return: The attribute
        """
        if self.__event.wait(self.__timeout):
            return getattr(self.__event.data, item)
        else:
            raise TemporalException("No service found before timeout")

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """
        Call the underlying object. Lets exception propagate
        """
        if self.__event.wait(self.__timeout):
            # We have a service: call it
            return cast(Callable[..., Any], self.__event.data)(*args, **kwargs)
        else:
            raise TemporalException("No service found before timeout")

    def __bool__(self) -> bool:
        """
        Boolean value of the proxy
        """
        return self.__event.is_set() and bool(self.__event.data)


class TemporalDependency(requires.SimpleDependency):
    """
    Manages a temporal dependency field
    """

    def __init__(self, field: str, requirement: Requirement, timeout: float) -> None:
        """
        Sets up the dependency

        :param field: Field where to inject the proxy
        :param requirement: Description of the required dependency
        :param timeout: Time to wait for a service (greater than 0, in seconds)
        """
        super(TemporalDependency, self).__init__(field, requirement)

        # Internal timeout
        self.__timeout = timeout

        # The delayed unbind timer
        self.__timer: Optional[threading.Timer] = None
        self.__timer_args: Optional[Tuple[Any, ...]] = None
        self.__still_valid = False

        # The injected value is the proxy
        self._value = _TemporalProxy(self.__timeout)

    def clear(self) -> None:
        """
        Cleans up the manager. The manager can't be used after this method has
        been called
        """
        # Cancel timer
        self.__cancel_timer()
        self.__timer = None
        self.__timer_args = None

        self.__still_valid = False
        self._value = None
        super(TemporalDependency, self).clear()

    def on_service_arrival(self, svc_ref: ServiceReference[Any]) -> None:
        """
        Called when a service has been registered in the framework

        :param svc_ref: A service reference
        """
        with self._lock:
            if self.reference is None:
                assert self._context is not None and self._ipopo_instance is not None

                # Inject the service
                service = self._context.get_service(svc_ref)
                self.reference = svc_ref
                self._value.set_service(service)
                self.__still_valid = True

                # Cancel timer
                self.__cancel_timer()

                # Bind the service
                self._ipopo_instance.bind(self, self._value, self.reference)

    def on_service_departure(self, svc_ref: ServiceReference[Any]) -> None:
        """
        Called when a service has been unregistered from the framework

        :param svc_ref: A service reference
        """
        with self._lock:
            if svc_ref is self.reference:
                # Forget about the service
                self._value.unset_service()

                # Clear the reference
                self.reference = None

                # Look for a replacement
                assert self._context is not None and self._ipopo_instance is not None

                self._pending_ref = self._context.get_service_reference(
                    self.requirement.specification, self.requirement.filter
                )

                if self._pending_ref is None:
                    # No replacement found yet, wait a little
                    self.__still_valid = True
                    self.__timer_args = (self._value, svc_ref)
                    self.__timer = threading.Timer(self.__timeout, self.__unbind_call, (False,))
                    self.__timer.start()
                else:
                    # Notify iPOPO immediately
                    self._ipopo_instance.unbind(self, self._value, svc_ref)

    def __cancel_timer(self) -> None:
        """
        Cancels the timer, and calls its target method immediately
        """
        if self.__timer is not None:
            self.__timer.cancel()
            self.__unbind_call(True)

        self.__timer_args = None
        self.__timer = None

    def __unbind_call(self, still_valid: bool) -> None:
        """
        Calls the iPOPO unbind method
        """
        with self._lock:
            if self.__timer is not None and self.__timer_args is not None:
                # Timeout expired, we're not valid anymore
                self.__timer = None
                self.__still_valid = still_valid
                assert self._ipopo_instance is not None
                self._ipopo_instance.unbind(self, self.__timer_args[0], self.__timer_args[1])

    def is_valid(self) -> bool:
        """
        Tests if the dependency is in a valid state
        """
        # Don't use the parent method: it will return true as the "_value"
        # member is not None
        return self.__still_valid or self._pending_ref is not None or self.requirement.optional
