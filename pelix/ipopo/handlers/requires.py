#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Dependency handler

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

import abc
import logging
import threading
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pelix.ipopo.constants as ipopo_constants
import pelix.ipopo.handlers.constants as constants
from pelix.constants import ActivatorProto, BundleActivator, BundleException
from pelix.framework import BundleContext
from pelix.internals.events import ServiceEvent
from pelix.internals.registry import ServiceListener, ServiceReference, ServiceRegistration
from pelix.ipopo.contexts import ComponentContext, Requirement
from pelix.ipopo.instance import StoredInstance

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class _HandlerFactory(constants.HandlerFactory):
    # pylint: disable=R0903
    """
    Factory service for service registration handlers
    """

    @staticmethod
    def _prepare_requirements(
        requirements: Dict[str, Requirement], requires_filters: Optional[Dict[str, str]]
    ) -> Dict[str, Requirement]:
        """
        Overrides the filters specified in the decorator with the given ones

        :param requirements: Dictionary of requirements (field → Requirement)
        :param requires_filters: Content of the 'requires.filter' component property (field → string)
        :return: The new requirements
        """
        if not requires_filters or not isinstance(requires_filters, dict):
            # No explicit filter configured
            return requirements

        # We need to change a part of the requirements
        new_requirements: Dict[str, Requirement] = {}
        for field, requirement in requirements.items():
            try:
                explicit_filter = requires_filters[field]

                # Store an updated copy of the requirement
                requirement_copy = requirement.copy()
                requirement_copy.set_filter(explicit_filter)
                new_requirements[field] = requirement_copy
            except (KeyError, TypeError, ValueError):
                # No information for this one, or invalid filter:
                # keep the factory requirement
                new_requirements[field] = requirement

        return new_requirements

    def get_handlers(self, component_context: ComponentContext, instance: Any) -> Iterable[constants.Handler]:
        """
        Sets up service providers for the given component

        :param component_context: The ComponentContext bean
        :param instance: The component instance
        :return: The list of handlers associated to the given component
        """
        # Extract information from the context
        requirements = component_context.get_handler(ipopo_constants.HANDLER_REQUIRES)
        requires_filters = component_context.properties.get(ipopo_constants.IPOPO_REQUIRES_FILTERS, None)

        # Prepare requirements
        requirements = self._prepare_requirements(requirements, requires_filters)

        # Set up the runtime dependency handlers
        handlers: List[constants.Handler] = []
        for field, requirement in requirements.items():
            # Construct the handler
            if requirement.aggregate:
                handlers.append(AggregateDependency(field, requirement))
            else:
                handlers.append(SimpleDependency(field, requirement))

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
        properties = {constants.PROP_HANDLER_ID: ipopo_constants.HANDLER_REQUIRES}

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


class _RuntimeDependency(constants.DependencyHandler, ServiceListener, abc.ABC):
    """
    Manages a required dependency field when a component is running
    """

    def __init__(self, field: str, requirement: Requirement) -> None:
        """
        Sets up the dependency

        :param field: The injected field name
        :param requirement: The Requirement describing this dependency
        """
        # The internal state lock
        self._lock: threading.RLock = threading.RLock()

        # The iPOPO StoredInstance object (given during manipulation)
        self._ipopo_instance: Optional[StoredInstance] = None

        # The bundle context
        self._context: Optional[BundleContext] = None

        # The associated field
        self._field: Optional[str] = field

        # The underlying requirement
        self.requirement: Requirement = requirement.copy()

        # Current field value
        self._value: Any = None

    def manipulate(self, stored_instance: StoredInstance, component_instance: Any) -> None:
        """
        Stores the given StoredInstance bean.

        :param stored_instance: The iPOPO component StoredInstance
        :param component_instance: The component instance
        """
        # Store the stored instance...
        self._ipopo_instance = stored_instance

        # ... and the bundle context
        self._context = stored_instance.bundle_context

    def clear(self) -> None:
        """
        Cleans up the manager. The manager can't be used after this method has
        been called
        """
        self._ipopo_instance = None
        self._context = None
        self._value = None
        self._field = None

    @abc.abstractmethod
    def get_bindings(self) -> List[ServiceReference[Any]]:
        ...

    def get_field(self) -> Optional[str]:
        return self._field

    def get_kinds(self) -> Iterable[str]:
        return (constants.KIND_DEPENDENCY,)

    def get_value(self) -> Any:
        return self._value

    def is_valid(self) -> bool:
        return (self.requirement is not None and self.requirement.optional) or self._value is not None

    @abc.abstractmethod
    def on_service_arrival(self, svc_ref: ServiceReference[Any]) -> Optional[bool]:
        """
        Called when a service has been registered in the framework

        :param svc_ref: A service reference
        :return: True if the service was accepted by the handler
        """
        ...

    @abc.abstractmethod
    def on_service_departure(self, svc_ref: ServiceReference[Any]) -> Optional[bool]:
        """
        Called when a service has been registered in the framework

        :param svc_ref: A service reference
        :return: True if the service departure was accepted by the handler
        """
        ...

    @abc.abstractmethod
    def on_service_modify(self, svc_ref: ServiceReference[Any], old_properties: Dict[str, Any]) -> None:
        """
        Called when a service has been registered in the framework

        :param svc_ref: A service reference
        :param old_properties: Previous properties values
        """
        ...

    def service_changed(self, event: ServiceEvent[Any]) -> None:
        if self._ipopo_instance is None or not self._ipopo_instance.check_event(event):
            # stop() and clean() may have been called after we have been put
            # inside a listener list copy...
            # or we've been told to ignore this event
            return

        # Call sub-methods
        kind = event.get_kind()
        svc_ref = event.get_service_reference()

        if kind == ServiceEvent.REGISTERED:
            # Service coming
            self.on_service_arrival(svc_ref)

        elif kind in (
            ServiceEvent.UNREGISTERING,
            ServiceEvent.MODIFIED_ENDMATCH,
        ):
            # Service gone or not matching anymore
            self.on_service_departure(svc_ref)

        elif kind == ServiceEvent.MODIFIED:
            # Modified properties (can be a new injection)
            self.on_service_modify(svc_ref, event.get_previous_properties() or {})

    def start(self) -> None:
        if self._context is None:
            raise ValueError("Bundle context not configured")

        if self.requirement is None:
            raise ValueError("Requirement not configured")

        self._context.add_service_listener(self, self.requirement.filter, self.requirement.specification)

    def stop(self) -> Optional[Iterable[Tuple[Any, ServiceReference[Any]]]]:
        if self._context is None:
            raise ValueError("Bundle context not configured")

        self._context.remove_service_listener(self)
        return None


class SimpleDependency(_RuntimeDependency):
    """
    Manages a simple dependency field
    """

    def __init__(self, field: str, requirement: Requirement) -> None:
        """
        Sets up the dependency
        """
        super(SimpleDependency, self).__init__(field, requirement)

        # We have only one reference to keep
        self.reference: Optional[ServiceReference[Any]] = None

        # Pending reference (to avoid double-lookup)
        self._pending_ref: Optional[ServiceReference[Any]] = None

    def clear(self) -> None:
        """
        Cleans up the manager. The manager can't be used after this method has
        been called
        """
        self.reference = None
        self._pending_ref = None
        super().clear()

    def get_bindings(self) -> List[ServiceReference[Any]]:
        """
        Retrieves the list of the references to the bound services

        :return: A list of ServiceReferences objects
        """
        with self._lock:
            if self.reference is not None:
                return [self.reference]

            return []

    def on_service_arrival(self, svc_ref: ServiceReference[Any]) -> Optional[bool]:
        """
        Called when a service has been registered in the framework

        :param svc_ref: A service reference
        """
        with self._lock:
            if self._value is None and self._context is not None and self._ipopo_instance is not None:
                # Inject the service
                self.reference = svc_ref
                self._value = self._context.get_service(svc_ref)

                self._ipopo_instance.bind(self, self._value, self.reference)
                return True

        return None

    def on_service_departure(self, svc_ref: ServiceReference[Any]) -> Optional[bool]:
        """
        Called when a service has been unregistered from the framework

        :param svc_ref: A service reference
        """
        with self._lock:
            if svc_ref is self.reference:
                service = self._value

                # Clear the instance values
                self._value = None
                self.reference = None

                if self._context is None:
                    raise ValueError("Bundle context not set")

                if self._ipopo_instance is None:
                    raise ValueError("StoredInstant not available")

                if self.requirement is not None and self.requirement.immediate_rebind:
                    # Look for a replacement
                    self._pending_ref = self._context.get_service_reference(
                        self.requirement.specification, self.requirement.filter
                    )

                self._ipopo_instance.unbind(self, service, svc_ref)
                return True

            return None

    def on_service_modify(self, svc_ref: ServiceReference[Any], old_properties: Dict[str, Any]) -> None:
        """
        Called when a service has been modified in the framework

        :param svc_ref: A service reference
        :param old_properties: Previous properties values
        """
        with self._lock:
            if self._ipopo_instance is None:
                raise ValueError("StoredInstance not available")

            if self.reference is None:
                # A previously registered service now matches our filter
                self.on_service_arrival(svc_ref)
            elif svc_ref is self.reference:
                # Notify the property modification
                self._ipopo_instance.update(self, self._value, svc_ref, old_properties)

    def stop(self) -> Optional[Iterable[Tuple[Any, ServiceReference[Any]]]]:
        """
        Stops the dependency manager (must be called before clear())

        :return: The removed bindings (list) or None
        """
        super(SimpleDependency, self).stop()
        if self.reference is not None:
            # Return a tuple of tuple
            return ((self._value, self.reference),)

        return None

    def is_valid(self) -> bool:
        """
        Tests if the dependency is in a valid state
        """
        return super(SimpleDependency, self).is_valid() or (
            self.requirement is not None
            and self.requirement.immediate_rebind
            and self._pending_ref is not None
        )

    def try_binding(self) -> None:
        """
        Searches for the required service if needed

        :raise BundleException: Invalid ServiceReference found
        """
        with self._lock:
            if self.reference is not None:
                # Already bound
                return

            if self._context is None:
                raise ValueError("BundleContext not set")

            if self.requirement is None:
                raise ValueError("Requirement not set")

            ref: Optional[ServiceReference[Any]]
            if self._pending_ref is not None:
                # Get the reference we chose to keep this component valid
                ref = self._pending_ref
                self._pending_ref = None
            else:
                # Get the first matching service
                ref = self._context.get_service_reference(
                    self.requirement.specification, self.requirement.filter
                )

            if ref is not None:
                # Found a service
                self.on_service_arrival(ref)


class AggregateDependency(_RuntimeDependency):
    """
    Manages an aggregated dependency field
    """

    def __init__(self, field: str, requirement: Requirement) -> None:
        """
        Sets up the dependency
        """
        super(AggregateDependency, self).__init__(field, requirement)

        # Reference -> Service
        self.services: Dict[ServiceReference[Any], Any] = {}

        # Future injected value
        self._future_value: Optional[List[Any]] = None

    def clear(self) -> None:
        """
        Cleans up the manager. The manager can't be used after this method has
        been called
        """
        self.services.clear()
        self._future_value = None
        super(AggregateDependency, self).clear()

    def get_bindings(self) -> List[ServiceReference[Any]]:
        """
        Retrieves the list of the references to the bound services

        :return: A list of ServiceReferences objects
        """
        with self._lock:
            return list(self.services.keys())

    def get_value(self) -> Any:
        """
        Retrieves the value to inject in the component

        :return: The value to inject
        """
        with self._lock:
            # The value field must be a copy of our list
            if self._future_value is not None:
                return self._future_value[:]

            return None

    def is_valid(self) -> bool:
        """
        Tests if the dependency is in a valid state
        """
        return (self.requirement is not None and self.requirement.optional) or self._future_value is not None

    def on_service_arrival(self, svc_ref: ServiceReference[Any]) -> Optional[bool]:
        """
        Called when a service has been registered in the framework

        :param svc_ref: A service reference
        """
        with self._lock:
            if svc_ref not in self.services:
                if self._context is None:
                    raise ValueError("BundleContext not set")

                if self._ipopo_instance is None:
                    raise ValueError("StoredInstance not set")

                # Get the new service
                service = self._context.get_service(svc_ref)

                if self._future_value is None:
                    # First value
                    self._future_value = []

                # Store the information
                self._future_value.append(service)
                self.services[svc_ref] = service

                self._ipopo_instance.bind(self, service, svc_ref)
                return True

            return None

    def on_service_departure(self, svc_ref: ServiceReference[Any]) -> Optional[bool]:
        """
        Called when a service has been unregistered from the framework

        :param svc_ref: A service reference
        :return: A tuple (service, reference) if the service has been lost, else None
        """
        with self._lock:
            try:
                # Get the service instance
                service = self.services.pop(svc_ref)
            except KeyError:
                # Not a known service reference: ignore
                pass
            else:
                if self._future_value:
                    # Clean the instance values
                    self._future_value.remove(service)

                # Nullify the value if needed
                if not self._future_value:
                    self._future_value = None

                if self._ipopo_instance is None:
                    raise ValueError("StoredInstance not set")

                self._ipopo_instance.unbind(self, service, svc_ref)
                return True

            return None

    def on_service_modify(self, svc_ref: ServiceReference[Any], old_properties: Dict[str, Any]) -> None:
        """
        Called when a service has been modified in the framework

        :param svc_ref: A service reference
        :param old_properties: Previous properties values
        """
        with self._lock:
            try:
                # Look for the service
                service = self.services[svc_ref]
            except KeyError:
                # A previously registered service now matches our filter
                self.on_service_arrival(svc_ref)
                return
            else:
                if self._ipopo_instance is None:
                    raise ValueError("StoredInstance not set")

                # Notify the property modification
                self._ipopo_instance.update(self, service, svc_ref, old_properties)

    def stop(self) -> Optional[List[Tuple[Any, ServiceReference[Any]]]]:
        """
        Stops the dependency manager (must be called before clear())

        :return: The removed bindings (list) or None
        """
        super(AggregateDependency, self).stop()

        if self.services:
            return [(service, reference) for reference, service in self.services.items()]

        return None

    def try_binding(self) -> None:
        """
        Searches for the required service if needed

        :raise BundleException: Invalid ServiceReference found
        """
        with self._lock:
            if self.services:
                # We already are alive (not our first call)
                # => we are updated through service events
                return

            if self._ipopo_instance is None or self._context is None or self.requirement is None:
                raise ValueError("Requirement not set")

            # Get all matching services
            refs: Optional[List[ServiceReference[Any]]] = self._context.get_all_service_references(
                self.requirement.specification, self.requirement.filter
            )
            if not refs:
                # No match found
                return

            results: List[ServiceReference[Any]] = []
            try:
                # Bind all new reference
                for reference in refs:
                    added = self.on_service_arrival(reference)
                    if added:
                        results.append(reference)
            except BundleException as ex:
                # Get the logger for this instance
                logger = logging.getLogger("-".join((self._ipopo_instance.name, "AggregateDependency")))
                logger.debug("Error binding multiple references: %s", ex)

                # Undo what has just been done, ignoring errors
                for reference in results:
                    try:
                        self.on_service_departure(reference)
                    except BundleException as ex2:
                        logger.debug("Error cleaning up: %s", ex2)

                del results[:]
                raise
