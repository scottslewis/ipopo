#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Discovery Provider API

:author: Scott Lewis
:copyright: Copyright 2020, Scott Lewis
:license: Apache License 2.0
:version: 1.0.2

..

    Copyright 2020 Scott Lewis

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
from threading import RLock
from typing import Any, Dict, List, Optional, Protocol, Tuple
from pelix.constants import Specification

from pelix.internals.registry import ServiceReference
from pelix.ipopo.decorators import BindField, Requires, UnbindField
from pelix.rsa import get_string_plus_property_value
from pelix.rsa.endpointdescription import EndpointDescription

# ------------------------------------------------------------------------------
# Module version

__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# Standard logging
_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


SERVICE_ENDPOINT_ADVERTISER = "pelix.rsa.discovery.endpointadvertiser"


@Specification(SERVICE_ENDPOINT_ADVERTISER)
class EndpointAdvertiser(abc.ABC):
    """
    Endpoint advertiser service specification.  EndpointAdvertiser services
    are used to advertise exported remote services.  See EndpointAdvertiser
    class below.
    """

    def __init__(self) -> None:
        self._published_endpoints: Dict[str, Tuple[EndpointDescription, Any]] = {}
        self._published_endpoints_lock = RLock()

    def advertise_endpoint(self, endpoint_description: EndpointDescription) -> bool:
        """
        Advertise and endpoint_description for remote discovery.
        If it hasn't already been a endpoint_description will be advertised via
        a some protocol.

        :param endpoint_description: an instance of EndpointDescription to
        advertise. Must not be None.
        :return: True if advertised, False if not
        (e.g. it's already been advertised)
        """
        endpoint_id = endpoint_description.get_id()
        with self._published_endpoints_lock:
            if self.get_advertised_endpoint(endpoint_id) is not None:
                return False

            advertise_result = self._advertise(endpoint_description)
            if advertise_result:
                self._add_advertised(endpoint_description, advertise_result)
                return True

            return False

    def update_endpoint(self, updated_ed: EndpointDescription) -> bool:
        """
        Update a previously advertised endpoint_description.

        :param endpoint_description: an instance of EndpointDescription to
        update. Must not be None.
        :return: True if advertised, False if not
        (e.g. it's already been advertised)
        """
        endpoint_id = updated_ed.get_id()
        with self._published_endpoints_lock:
            if self.get_advertised_endpoint(endpoint_id) is None:
                return False

            advertise_result = self._update(updated_ed)
            if advertise_result:
                self._remove_advertised(endpoint_id)
                self._add_advertised(updated_ed, advertise_result)
                return True

            return False

    def unadvertise_endpoint(self, endpointid: str) -> bool:
        """
        Unadvertise a previously-advertised endpointid (string).

        :param endpointid.  The string returned from ed.get_id() or
        the value of property endpoint.id.  Should not be None

        :return True if removed, False if not removed (hasn't been previously advertised
        by this advertiser
        """
        with self._published_endpoints_lock:
            advertised = self.get_advertised_endpoint(endpointid)
            if not advertised:
                return False

            unadvertise_result = self._unadvertise(advertised)
            if unadvertise_result:
                self._remove_advertised(endpointid)

            return True

    def is_advertised(self, endpointid: str) -> bool:
        """
        Is given endpointid been advertised by this advertiser.

        :param endpointid.  The string returned from ed.get_id() or the value
        of property endpoint.id.  Should not be None.
        :return True if the given endpointid has previously been
        advertised (and not unadvertised) by this advertiser
        """
        return self.get_advertised_endpoint(endpointid) is not None

    def get_advertised_endpoint(self, endpointid: str) -> Optional[Tuple[EndpointDescription, Any]]:
        """
        Get the advertised endpoint given endpointid.

        :param endpointid.  The string reeturned from ed.get_id() or the value
        of property endpoint.id.  Should not be None.

        :return tuple/2 with (endpoint_description,advertise_result), or
        None.
        """
        with self._published_endpoints_lock:
            return self._published_endpoints.get(endpointid, None)

    def get_advertised_endpoints(self) -> Dict[str, Tuple[EndpointDescription, Any]]:
        """
        Get all endpoints advertised by this advertiser.

        :returns dictionary of tuple/2 (endpoint_description,advertise_result).
        May return empty dictionary.
        """
        with self._published_endpoints_lock:
            return self._published_endpoints.copy()

    def _add_advertised(self, ed: EndpointDescription, advertise_result: Any) -> None:
        with self._published_endpoints_lock:
            self._published_endpoints[ed.get_id()] = (ed, advertise_result)

    def _remove_advertised(self, endpointid: str) -> Optional[Tuple[EndpointDescription, Any]]:
        with self._published_endpoints_lock:
            return self._published_endpoints.pop(endpointid, None)

    @abc.abstractmethod
    def _advertise(self, endpoint_description: EndpointDescription) -> Any:
        """
        Advertise a new endpoint description.
        Result is implementation dependent.
        """

    @abc.abstractmethod
    def _update(self, endpoint_description: EndpointDescription) -> Any:
        """
        Advertise the update of an endpoint description.
        Result is implementation dependent.
        """

    @abc.abstractmethod
    def _unadvertise(self, advertised: Tuple[EndpointDescription, Any]) -> Any:
        """
        Advertise the removal of an endpoint description.
        Result is implementation dependent.
        """


# ------------------------------------------------------------------------------
# EndpointEvent implementation used to provide EndpointEventListener service
# instances with valid EndpointEvent by endpoint advertisers


class EndpointEvent:
    """
    EndpointEvents are used by endpoint advertisers to call
    EndpointEventListeners with the type of event (ADDED,REMOVED,MODIFIED)
    and the associated EndpointDescription.
    """

    ADDED = 1
    REMOVED = 2
    MODIFIED = 4

    def __init__(self, event_type: int, endpoint_description: EndpointDescription) -> None:
        self._type = event_type
        self._ed = endpoint_description

    def get_type(self) -> int:
        """
        Get the type of the EndpointEvent (ADDED|REMOVED|MODIFIED).

        :return event type (int)
        """
        return self._type

    def get_endpoint_description(self) -> EndpointDescription:
        """
        Get the EndpointDescription associated with this event.

        :return EndpointDescription instance associated with this event.
        """
        return self._ed

    def __str__(self) -> str:
        return f"EndpointEvent(type={self._type},ed={self._ed})"


# ------------------------------------------------------------------------------
# Endpoint listener service specification
# This service specification is exposed by instances that wish to be
# notified by discovery providers when an EndpointEvent has occurred.
# For example, TopologyManagers will typically expose themselves as
# a service endpoint listener so that discovery subscribers can
# notify all such services when an endpoint event has been received.

SERVICE_ENDPOINT_LISTENER = "pelix.rsa.discovery.endpointeventlistener"
SERVICE_ENDPOINT_EVENT_LISTENER = SERVICE_ENDPOINT_LISTENER


@Specification(SERVICE_ENDPOINT_EVENT_LISTENER)
class EndpointEventListener(Protocol):
    """
    Subclasses should override the endpoint_changed method
    so that they will receive notification (via an arbitrary
    thread) when an endpoint has been added, removed or modified
    """

    # Endpoint listener scope will be consulted when a
    # discovery provider receives an endpoint event.
    # The service that provides the SERVICE_ENDPOINT_LISTENER
    # specification should provided a ldap filter (or array of
    # filters) for filtering the endpoint description properties
    # against the filter for delivery.  For example, an implementer
    # of this service could define as one of its properties:
    # ENDPOINT_LISTENER_SCOPE: '(*=*)'
    # Such a filter will receive all endpoint notifications because
    # the filter '(*=*)' matches any set of endpoint description
    # properties.  If the filter matches the properties, then
    # the endpoint_changed method will be called
    ENDPOINT_LISTENER_SCOPE: str = "endpoint.listener.scope"

    def endpoint_changed(self, endpoint_event: EndpointEvent, matched_filter: Optional[str]) -> None:
        """
        Called by discovery providers when an endpoint has been
        ADDED,REMOVED or MODIFIED.

        :param endpoint_event an instance of EndpointEvent.  Will
        not be None.
        :param matched_filter the filter (as string) that matched
        this endpoint event listener service instance.
        """
        ...


@Requires("_event_listeners", EndpointEventListener, True, True)
class EndpointSubscriber(abc.ABC):
    """
    Utility superclass for EndpointSubscribers.
    """

    def __init__(self) -> None:
        self._endpoint_event_listeners: List[
            Tuple[EndpointEventListener, ServiceReference[EndpointEventListener]]
        ] = []
        self._endpoint_event_listeners_lock = RLock()
        self._discovered_endpoints: Dict[str, Tuple[str, EndpointDescription]] = {}
        self._discovered_endpoints_lock = RLock()

    @BindField("_event_listeners")
    def _add_endpoint_event_listener(
        self,
        field: str,
        listener: EndpointEventListener,
        service_ref: ServiceReference[EndpointEventListener],
    ) -> None:
        with self._endpoint_event_listeners_lock:
            self._endpoint_event_listeners.append((listener, service_ref))

    @UnbindField("_event_listeners")
    def _remove_endpoint_event_listener(
        self,
        field: str,
        listener: EndpointEventListener,
        service_ref: ServiceReference[EndpointEventListener],
    ) -> None:
        with self._endpoint_event_listeners_lock:
            try:
                return self._endpoint_event_listeners.remove((listener, service_ref))
            except Exception:
                pass

    def _get_matching_endpoint_event_listeners(
        self, ed: EndpointDescription
    ) -> List[Tuple[EndpointEventListener, str]]:
        result = []
        with self._discovered_endpoints_lock:
            ls = self._endpoint_event_listeners[:]
        for l in ls:
            svc_ref = l[1]
            filters = get_string_plus_property_value(
                svc_ref.get_property(EndpointEventListener.ENDPOINT_LISTENER_SCOPE)
            )
            matching_filter = None
            if filters:
                for f in filters:
                    if ed.matches(f):
                        matching_filter = f
                        break
            if matching_filter:
                result.append((l[0], matching_filter))
        return result

    def _has_discovered_endpoint(self, ed_id: str) -> Optional[EndpointDescription]:
        with self._discovered_endpoints_lock:
            ep = self._discovered_endpoints.get(ed_id, None)
            if ep:
                return ep[1]

            return None

    def _get_endpointids_for_sessionid(self, sessionid: str) -> List[str]:
        result: List[str] = []
        with self._discovered_endpoints_lock:
            for epid, ep in self._discovered_endpoints.items():
                if ep and sessionid == ep[0]:
                    result.append(epid)
        return result

    def _add_discovered_endpoint(self, sessionid: str, ed: EndpointDescription) -> None:
        with self._discovered_endpoints_lock:
            _logger.debug("_add_discovered_endpoint ed=%s", ed)
            self._discovered_endpoints[ed.get_id()] = (sessionid, ed)

    def _remove_discovered_endpoint(self, endpointid: str) -> Optional[EndpointDescription]:
        with self._discovered_endpoints_lock:
            node = self._discovered_endpoints.pop(endpointid, None)
            if node:
                return node[1]

            return None

    def _fire_endpoint_event(self, event_type: int, ed: EndpointDescription) -> None:
        listeners = self._get_matching_endpoint_event_listeners(ed)
        if not listeners:
            logging.error(
                "EndpointSubscriber._fire_endpoint_event found no matching "
                "listeners for event_type=%s and endpoint=%s",
                event_type,
                ed,
            )
            return

        event = EndpointEvent(event_type, ed)
        for listener in listeners:
            try:
                listener[0].endpoint_changed(event, listener[1])
            except Exception:
                _logger.exception(
                    "Exception calling endpoint event "
                    "listener.endpoint_changed for listener=%s and event=%s",
                    listener,
                    event,
                )
