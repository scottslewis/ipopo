#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
An EventAdmin-like implementation for Pelix: a publish-subscribe service

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

import copy
import fnmatch
import logging
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union, cast

import pelix.constants
import pelix.framework
import pelix.ldapfilter
import pelix.services
import pelix.threadpool
from pelix.internals.registry import ServiceReference
from pelix.ipopo.decorators import ComponentFactory, Invalidate, Property, Provides, Validate
from pelix.utilities import to_iterable

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


@ComponentFactory(pelix.services.FACTORY_EVENT_ADMIN)
@Provides(pelix.services.EventAdmin)
@Property("_nb_threads", "pool.threads", 10)
class EventAdmin(pelix.services.EventAdmin):
    """
    The EventAdmin implementation
    """

    def __init__(self) -> None:
        # The bundle context
        self._context: Optional[pelix.framework.BundleContext] = None

        # The framework instance UID
        self._fw_uid: Optional[str] = None

        # Number of threads in the pool
        self._nb_threads: int = 10

        # Thread pool
        self._pool: Optional[pelix.threadpool.ThreadPool] = None

    def _get_handlers_ids(self, topic: str, properties: Dict[str, Any]) -> Optional[List[str]]:
        """
        Retrieves the IDs of the listeners that requested to handle this event

        :param topic: Topic of the event
        :param properties: Associated properties
        :return: The IDs of the services to call back for this event. None if none found
        """
        handlers: List[str] = []

        # Get the handler service references
        assert self._context is not None
        handlers_refs = self._context.get_all_service_references(pelix.services.ServiceEventHandler, None)

        if handlers_refs is None:
            # No service found
            return None

        for svc_ref in handlers_refs:
            # Check the LDAP filter
            ldap_filter = svc_ref.get_property(pelix.services.PROP_EVENT_FILTER)
            if self.__match_filter(properties, ldap_filter):
                # Get the service ID
                svc_id = svc_ref.get_property(pelix.constants.SERVICE_ID)

                # Filter matches the event, test the topic
                topics = to_iterable(svc_ref.get_property(pelix.services.PROP_EVENT_TOPICS), True)
                if not topics:
                    # Filter matches, and no topic filter given: notify it
                    handlers.append(svc_id)
                else:
                    for handled_topic in cast(Iterable[str], to_iterable(topics, False)):
                        if fnmatch.fnmatch(topic, handled_topic):
                            # Full match, keep the service ID
                            handlers.append(svc_id)
                            break

        return handlers

    @staticmethod
    def __match_filter(
        properties: Dict[str, Any], ldap_filter: Union[None, str, pelix.ldapfilter.LdapFilterOrCriteria]
    ) -> bool:
        """
        Tests if the given properties match the given filter

        :param properties: A set of properties
        :param ldap_filter: An LDAP filter string, object or None
        :return: True if the properties match the filter
        """
        if not ldap_filter:
            # No filter
            return True

        # Normalize the filter
        ldap_filter = pelix.ldapfilter.get_ldap_filter(ldap_filter)
        return ldap_filter is None or ldap_filter.matches(properties)

    def __get_service(
        self, service_id: str
    ) -> Tuple[
        Optional[ServiceReference[pelix.services.ServiceEventHandler]],
        Optional[pelix.services.ServiceEventHandler],
    ]:
        """
        Retrieves the reference and the service associated to the given ID,
        or a (None, None) tuple if no service was found.

        The service must be freed with BundleContext.unget_service() after
        usage

        :param service_id: A service ID
        :return: A (reference, service) tuple or (None, None)
        """
        try:
            # Prepare the filter
            ldap_filter = f"({pelix.constants.SERVICE_ID}={service_id})"

            # Get the reference
            assert self._context is not None
            ref = self._context.get_service_reference(pelix.services.ServiceEventHandler, ldap_filter)
            if ref is None:
                # Unknown service
                return None, None

            # Get the service
            return ref, self._context.get_service(ref)
        except pelix.constants.BundleException:
            # Service disappeared
            return None, None

    def __notify_handlers(self, topic: str, properties: Dict[str, Any], handlers_ids: Iterable[str]) -> None:
        """
        Notifies the handlers of an event

        :param topic: Topic of the event
        :param properties: Associated properties
        :param handlers_ids: IDs of the services to notify
        """
        if self._context is None:
            # No more context
            return

        for handler_id in handlers_ids:
            # Define the "ref" variable name (and reset it on each loop)
            ref = None
            try:
                # Get the service
                ref, handler = self.__get_service(handler_id)
                if handler is not None:
                    # Use a copy of the properties each time
                    handler.handle_event(topic, copy.deepcopy(properties))
            except Exception as ex:
                _logger.exception(
                    "Error notifying event handler %d: %s (%s)",
                    handler_id,
                    ex,
                    type(ex).__name__,
                )
            finally:
                if ref is not None:
                    self._context.unget_service(ref)

    def __setup_properties(self, properties: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Adds the EventAdmin specific properties to the event

        :param properties: The initial event properties
        :return: A copy of the initial properties, or new ones, with the EventAdmin specific properties
        """
        # Compute the event time stamp
        timestamp = time.time()

        if not isinstance(properties, dict):
            # Create a new dictionary
            props: Dict[str, Any] = {}

        else:
            # Copy the given one
            props = properties.copy()

        # ... event time stamp
        props[pelix.services.EVENT_PROP_TIMESTAMP] = timestamp

        # ... framework UID
        props[pelix.services.EVENT_PROP_FRAMEWORK_UID] = self._fw_uid

        return props

    def send(self, topic: str, properties: Optional[Dict[str, Any]] = None) -> None:
        """
        Sends synchronously the given event

        :param topic: Topic of event
        :param properties: Associated properties
        """
        # Compute properties
        properties = self.__setup_properties(properties)

        # Get the currently available handlers
        handlers_ids = self._get_handlers_ids(topic, properties)
        if handlers_ids:
            # Notify them
            self.__notify_handlers(topic, properties, handlers_ids)

    def post(self, topic: str, properties: Optional[Dict[str, Any]] = None) -> None:
        """
        Sends asynchronously the given event

        :param topic: Topic of event
        :param properties: Associated properties
        """
        # Compute properties
        properties = self.__setup_properties(properties)

        # Get the currently available handlers
        handlers_ids = self._get_handlers_ids(topic, properties)
        if handlers_ids:
            # Enqueue the task in the thread pool
            assert self._pool is not None
            self._pool.enqueue(self.__notify_handlers, topic, properties, handlers_ids)

    @Validate
    def validate(self, context: pelix.framework.BundleContext) -> None:
        """
        Component validated
        """
        # Store the bundle context
        self._context = context

        # Get the framework instance UID
        self._fw_uid = cast(Optional[str], context.get_property(pelix.constants.FRAMEWORK_UID))

        # Normalize properties
        try:
            self._nb_threads = int(self._nb_threads)
            if self._nb_threads < 2:
                # Minimal value
                self._nb_threads = 2
        except ValueError:
            # Default value
            self._nb_threads = 10

        # Create the thread pool
        self._pool = pelix.threadpool.ThreadPool(self._nb_threads, logname="eventadmin-pool")
        self._pool.start()

    @Invalidate
    def invalidate(self, context: pelix.framework.BundleContext) -> None:
        """
        Component invalidated
        """
        # Stop the thread pool (empties its queue)
        if self._pool is not None:
            self._pool.stop()
            self._pool = None

        # Forget the bundle context
        self._context = None
        self._fw_uid = None
