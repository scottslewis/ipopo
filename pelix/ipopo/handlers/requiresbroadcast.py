#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
RequiresBroadcast handler implementation

:author: Thomas Calmant
:copyright: Copyright 2023, Thomas Calmant
:license: Apache License 2.0
:version: 1.0.2

..

    Copyright 2020 Thomas Calmant

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

# Standard library
import logging
import threading

# Pelix beans
from pelix.constants import BundleActivator, BundleException
from pelix.internals.events import ServiceEvent

# iPOPO constants
import pelix.ipopo.constants as ipopo_constants
import pelix.ipopo.handlers.constants as constants
import pelix.ipopo.handlers.requires as requires

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class _HandlerFactory(requires._HandlerFactory):
    # pylint: disable=W0212, R0903
    """
    Factory service for service registration handlers
    """

    def get_handlers(self, component_context, instance):
        """
        Sets up service providers for the given component

        :param component_context: The ComponentContext bean
        :param instance: The component instance
        :return: The list of handlers associated to the given component
        """
        # Extract information from the context
        requirements = component_context.get_handler(
            ipopo_constants.HANDLER_REQUIRES_BRODCAST
        )
        requires_filters = component_context.properties.get(
            ipopo_constants.IPOPO_REQUIRES_FILTERS, None
        )

        # Prepare requirements
        requirements = self._prepare_requirements(
            requirements, requires_filters
        )

        # Set up the runtime dependency handlers
        handlers = []
        for field, config in requirements.items():
            # Extract values from tuple
            requirement, muffle_ex, trace_ex = config

            # Construct the handler
            handlers.append(
                BroadcastDependency(field, requirement, muffle_ex, trace_ex)
            )

        return handlers


@BundleActivator
class _Activator(object):
    """
    The bundle activator
    """

    def __init__(self):
        """
        Sets up members
        """
        self._registration = None

    def start(self, context):
        """
        Bundle started
        """
        # Set up properties
        properties = {
            constants.PROP_HANDLER_ID: ipopo_constants.HANDLER_REQUIRES_BRODCAST
        }

        # Register the handler factory service
        self._registration = context.register_service(
            constants.SERVICE_IPOPO_HANDLER_FACTORY,
            _HandlerFactory(),
            properties,
        )

    def stop(self, _):
        """
        Bundle stopped
        """
        # Unregister the service
        self._registration.unregister()
        self._registration = None


# ------------------------------------------------------------------------------


class _ProxyDummy(object):
    """
    Dummy "Yes Man" object
    """

    def __init__(self, handler, name):
        """
        :param handler: The parent BroadcastHandler
        :param name: Name of this field
        """
        self.__handler = handler
        self.__name = name

    def __bool__(self):
        """
        Returns True if at least one service is bound
        """
        return self.__handler.has_services()

    # Python 2 compatibility
    __nonzero__ = __bool__

    def __call__(self, *args, **kwargs):
        """
        We have to handle a call
        """
        return self.__handler.handle_call(self.__name, args, kwargs)

    def __getattr__(self, member):
        """
        Recursive proxy
        """
        if self.__name is not None:
            member = "{0}.{1}".format(self.__name, member)

        return _ProxyDummy(self.__handler, member)


# ------------------------------------------------------------------------------


class BroadcastDependency(constants.DependencyHandler):
    """
    Manages a required dependency field when a component is running
    """

    def __init__(self, field, requirement, muffle_exceptions, trace_exceptions):
        """
        Sets up the dependency

        :param field: The injected field name
        :param requirement: The Requirement describing this dependency
        :param muffle_exceptions: Flag to not propagate exceptions
        :param proxy_class: Class to use to emulate the missing requirement
        """
        # The internal state lock
        self._lock = threading.RLock()

        # The iPOPO StoredInstance object (given during manipulation)
        self._ipopo_instance = None

        # The bundle context
        self._context = None

        # The associated field
        self._field = field

        # The underlying requirement
        self.requirement = requirement

        # Exception handling flags
        self._muffle_ex = muffle_exceptions
        self._trace_ex = trace_exceptions

        # Injected proxy
        self._proxy = _ProxyDummy(self, None)

        # The logger
        self._logger = logging.getLogger(
            "-".join(("<n/a>", "RequiresBroadcast", field))
        )

        # Reference -> Service
        self._services = {}

        # Length of the future injected list
        self._future_len = 0

    def manipulate(self, stored_instance, component_instance):
        """
        Stores the given StoredInstance bean.

        :param stored_instance: The iPOPO component StoredInstance
        :param component_instance: The component instance
        """
        # Store the stored instance...
        self._ipopo_instance = stored_instance

        # ... and the bundle context
        self._context = stored_instance.bundle_context

        # Reset the logger
        self._logger = logging.getLogger(
            "-".join(
                (self._ipopo_instance.name, "RequiresBroadcast", self._field)
            )
        )

        # Set the default value for the field if it is optional: the proxy
        if self.requirement.optional:
            setattr(component_instance, self._field, self._proxy)

    def clear(self):
        """
        Cleans up the manager. The manager can't be used after this method has
        been called
        """
        self._services.clear()

        self.requirement = None
        self._services = None
        self._future_len = 0
        self._lock = None
        self._field = None
        self._ipopo_instance = None
        self._context = None
        self._muffle_ex = False
        self._trace_ex = False
        self._proxy = None

    def get_bindings(self):
        """
        Retrieves the list of the references to the bound services

        :return: A list of ServiceReferences objects
        """
        with self._lock:
            return list(self._services.keys())

    def get_field(self):
        """
        Returns the name of the field handled by this handler
        """
        return self._field

    def get_kinds(self):
        """
        Retrieves the kinds of this handler: 'dependency'

        :return: the kinds of this handler
        """
        return (constants.KIND_DEPENDENCY,)

    def get_value(self):
        """
        Retrieves the value to inject in the component

        :return: The value to inject
        """
        if self._future_len > 0 or (
            self.requirement is not None and self.requirement.optional
        ):
            # We got something to work on
            return self._proxy

        # Invalid state
        return None

    def is_valid(self):
        """
        Tests if the dependency is in a valid state
        """
        return (
            self.requirement is not None and self.requirement.optional
        ) or self._future_len > 0

    def has_services(self):
        """
        Indicates if at least one service is bound (used by the proxy)
        """
        return self._future_len > 0

    def on_service_arrival(self, svc_ref):
        """
        Called when a service has been registered in the framework

        :param svc_ref: A service reference
        """
        with self._lock:
            if svc_ref in self._services:
                # We already know this service
                return False

            # Keep track of the service
            svc = self._services[svc_ref] = self._context.get_service(svc_ref)
            self._future_len += 1

            # Bind it
            self._ipopo_instance.bind(self, svc, svc_ref)
            return True

    def on_service_departure(self, svc_ref):
        """
        Called when a service has been unregistered from the framework

        :param svc_ref: A service reference
        """
        with self._lock:
            try:
                svc = self._services[svc_ref]
            except KeyError:
                # Unknown reference
                return None

            # Future length decreases
            self._future_len -= 1

            # Unbind the service first (to keep access during invalidate)
            self._ipopo_instance.unbind(self, svc, svc_ref)

            try:
                # Clean up
                del self._services[svc_ref]
            except KeyError:
                # Ignore, as it might be a side effect
                pass

            return True

    def service_changed(self, event):
        """
        Called by the framework when a service event occurs
        """
        if (
            self._ipopo_instance is None
            or not self._ipopo_instance.check_event(event)
        ):
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

    def start(self):
        """
        Starts the dependency manager
        """
        self._context.add_service_listener(
            self, self.requirement.filter, self.requirement.specification
        )

    def stop(self):
        """
        Stops the dependency manager (must be called before clear())

        :return: The removed bindings (list) or None
        """
        self._context.remove_service_listener(self)
        if self._services:
            return [
                (service, reference)
                for reference, service in self._services.items()
            ]

        return None

    def try_binding(self):
        """
        Searches for the required service if needed

        :raise BundleException: Invalid ServiceReference found
        """
        with self._lock:
            if self._services:
                # We already are alive (not our first call)
                # => we are updated through service events
                return

            # Get all matching services
            refs = self._context.get_all_service_references(
                self.requirement.specification, self.requirement.filter
            )
            if not refs:
                # No match found
                return

            results = []
            try:
                # Bind all new reference
                for reference in refs:
                    added = self.on_service_arrival(reference)
                    if added:
                        results.append(reference)
            except BundleException as ex:
                self._logger.debug("Error binding multiple references: %s", ex)

                # Undo what has just been done, ignoring errors
                for reference in results:
                    try:
                        self.on_service_departure(reference)
                    except BundleException as ex2:
                        self._logger.debug("Error cleaning up: %s", ex2)

                del results[:]
                raise

    def handle_call(self, members_str, args, kwargs):
        """
        Handles a call to the proxy
        """
        if members_str:
            all_members = members_str.split(".")
        else:
            all_members = []

        with self._lock:
            if not self._services:
                # Nothing we can do: return False
                return False

            # Copy the list, just in case we have a side effect
            for svc in list(self._services.values()):
                try:
                    # Find the element to call
                    to_call = svc
                    for member in all_members:
                        to_call = getattr(to_call, member)
                except AttributeError:
                    self._logger.warning("%s as no %s member", svc, members_str)
                else:
                    try:
                        # Call it
                        to_call(*args, **kwargs)
                    except Exception as ex:  # pylint:disable=broad-except
                        if not self._muffle_ex:
                            # Propagate if requested
                            raise ex

                        if self._trace_ex:
                            # Log it
                            self._logger.exception(ex)

            # Service have been notified (or failed silently): return True
            return True
