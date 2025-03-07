#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
RemoteServiceAdmin constants and utility functions

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

import collections.abc
import threading
import time
import uuid
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
    TypeVar,
    Union,
    cast,
)

from pelix import constants
from pelix.framework import Bundle, BundleContext
from pelix.internals.registry import ServiceReference

if TYPE_CHECKING:
    from pelix.rsa.endpointdescription import EndpointDescription

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

K = TypeVar("K")
T = TypeVar("T")

# ------------------------------------------------------------------------------

# RSA constants, declared in org.osgi.service.remoteserviceadmin.RemoteConstants
ENDPOINT_ID = "endpoint.id"
ENDPOINT_SERVICE_ID = "endpoint.service.id"
ENDPOINT_FRAMEWORK_UUID = "endpoint.framework.uuid"
ENDPOINT_PACKAGE_VERSION_ = "endpoint.package.version."
SERVICE_EXPORTED_INTERFACES = "service.exported.interfaces"
REMOTE_CONFIGS_SUPPORTED = "remote.configs.supported"
REMOTE_INTENTS_SUPPORTED = "remote.intents.supported"
SERVICE_EXPORTED_CONFIGS = "service.exported.configs"
SERVICE_EXPORTED_INTENTS = "service.exported.intents"
SERVICE_EXPORTED_INTENTS_EXTRA = "service.exported.intents.extra"
SERVICE_IMPORTED = "service.imported"
SERVICE_IMPORTED_CONFIGS = "service.imported.configs"
SERVICE_INTENTS = "service.intents"
SERVICE_ID = "service.id"
OBJECT_CLASS = "objectClass"
SERVICE_BUNDLE_ID = "service.bundleid"
INSTANCE_NAME = "instance.name"
SERVICE_RANKING = "service.ranking"
SERVICE_COMPONENT_NAME = "component.name"
SERVICE_COMPONENT_ID = "component.id"
# R7 standardized intents
OSGI_BASIC_INTENT = "osgi.basic"
OSGI_BASIC_TIMEOUT_INTENT = f"{OSGI_BASIC_INTENT}.timeout"
OSGI_ASYNC_INTENT = "osgi.async"
OSGI_CONFIDENTIAL_INTENT = "osgi.confidential"
OSGI_PRIVATE_INTENT = "osgi.private"
# List of them
RSA_PROP_NAMES = [
    ENDPOINT_ID,
    ENDPOINT_SERVICE_ID,
    ENDPOINT_FRAMEWORK_UUID,
    SERVICE_EXPORTED_INTERFACES,
    REMOTE_CONFIGS_SUPPORTED,
    REMOTE_INTENTS_SUPPORTED,
    SERVICE_EXPORTED_CONFIGS,
    SERVICE_EXPORTED_INTENTS,
    SERVICE_EXPORTED_INTENTS_EXTRA,
    SERVICE_IMPORTED,
    SERVICE_IMPORTED_CONFIGS,
    SERVICE_INTENTS,
    SERVICE_ID,
    OBJECT_CLASS,
    INSTANCE_NAME,
    SERVICE_RANKING,
    SERVICE_COMPONENT_ID,
    SERVICE_COMPONENT_NAME,
]

# ECF constants
ECF_ENDPOINT_CONTAINERID_NAMESPACE = "ecf.endpoint.id.ns"
ECF_ENDPOINT_ID = "ecf.endpoint.id"
ECF_RSVC_ID = "ecf.rsvc.id"
ECF_ENDPOINT_TIMESTAMP = "ecf.endpoint.ts"
ECF_ENDPOINT_CONNECTTARGET_ID = "ecf.endpoint.connecttarget.id"
ECF_ENDPOINT_IDFILTER_IDS = "ecf.endpoint.idfilter.ids"
ECF_ENDPOINT_REMOTESERVICE_FILTER = "ecf.endpoint.rsfilter"
ECF_SERVICE_EXPORTED_CONTAINER_FACTORY_ARGS = "ecf.exported.containerfactoryargs"
ECF_SERVICE_EXPORTED_CONTAINER_CONNECT_CONTEXT = "ecf.exported.containerconnectcontext"
ECF_SERVICE_EXPORTED_CONTAINER_ID = "ecf.exported.containerid"
ECF_SERVICE_EXPORTED_ASYNC_INTERFACES = "ecf.exported.async.interfaces"
ECF_SERVICE_EXPORTED_ASYNC_NOPROXY = "ecf.rsvc.async.noproxy"
ECF_SERVICE_ASYNC_RSPROXY_CLASS_ = "ecf.rsvc.async.proxy_"
ECF_ASYNC_INTERFACE_SUFFIX = "Async"
ECF_SERVICE_IMPORTED_VALUETYPE = "ecf.service.imported.valuetype"
ECF_SERVICE_IMPORTED_ENDPOINT_ID = ENDPOINT_ID
ECF_SERVICE_IMPORTED_ENDPOINT_SERVICE_ID = ENDPOINT_SERVICE_ID
ECF_OSGI_ENDPOINT_MODIFIED = "ecf.osgi.endpoint.modified"
ECF_OSGI_CONTAINER_ID_NS = "ecf.osgi.ns"
# List
ECFPROPNAMES = [
    ECF_ENDPOINT_CONTAINERID_NAMESPACE,
    ECF_ENDPOINT_ID,
    ECF_RSVC_ID,
    ECF_ENDPOINT_TIMESTAMP,
    ECF_ENDPOINT_CONNECTTARGET_ID,
    ECF_ENDPOINT_IDFILTER_IDS,
    ECF_ENDPOINT_REMOTESERVICE_FILTER,
    ECF_SERVICE_EXPORTED_ASYNC_INTERFACES,
    ECF_SERVICE_IMPORTED_VALUETYPE,
]

ERROR_EP_ID = "0"
ERROR_NAMESPACE = "org.eclipse.ecf.core.identity.StringID"
ERROR_IMPORTED_CONFIGS = ["import.error.config"]
ERROR_ECF_EP_ID = "export.error.id"
DEFAULT_EXPORTED_CONFIGS = ["ecf.xmlrpc.server"]

IPOPO_ECF_NAMESPACE = "ecf.ipopo"

# ------------------------------------------------------------------------------
## RSA Service API
# ------------------------------------------------------------------------------

SERVICE_REMOTE_SERVICE_ADMIN = "pelix.rsa.remoteserviceadmin"


@constants.Specification(SERVICE_REMOTE_SERVICE_ADMIN)
class RemoteServiceAdmin(Protocol):
    """
    RSA service specification.  This specification is the core service
    implemented by the RSA package.  See the RemoteServiceAdmin
    class below for method documentation.
    """

    def get_exported_services(self) -> List["ExportReference"]:
        """
        Get services previously exported by this RSA implementation.  Will
        not return None, but may return empty list.

        :return list of ExportReference instances.  See ExportReference class.
        """
        ...

    def get_imported_endpoints(self) -> List["ImportReference"]:
        """
        Get services previously imported by this RSA implementation.  Will
        not return None, but may return empty list.

        :return list of ImportReference instances.  See ImpportReference class.
        """
        ...

    def export_service(
        self, service_ref: ServiceReference[Any], overriding_props: Optional[Dict[str, Any]] = None
    ) -> List["ExportRegistration"]:
        """
        Export a given service_ref (ServiceReference) using overriding_props
        dictionary. service_ref must not be None and must be of type
        ServiceReference.  If overriding_props is provided,
        then the properties set in overriding_props will override those
        from service_ref.get_properties().  The RSA-specified props
        (e.g. service.exported.interfaces,service.exported.configs,
        service.exported.intents) will then be used to determine whether
        to export the service, and which ExportDistributionProvider
        services to use for exporting the service.

        :param service_ref a service to export.  Must not be None and
        must be of type ServiceReference
        :param overriding_props if not None, any props given will
        override those provided in service_ref
        :return list of ExportRegistration instances.  See ExportRegistration
        class.
        """
        ...

    def import_service(self, endpoint_description: "EndpointDescription") -> "ImportRegistration":
        """
        Import a given endpoint_description.  Must not be None, and must
        be of type EndpointDescription.  The endpoint_description props
        (e.g. service.exported.configs, service.imported.configs, etc,
        service.intents) will then be used to determine whether
        to import the service, and which ImportDistributionProvider
        service to use for importing the service.

        :param endpoint_description to import.  Must not be None.
        Must be of type EndpointDescription
        :return a single ImportRegistration used to import the
        endpoint_description.  See ImportRegistration class
        """
        ...


# ------------------------------------------------------------------------------


class ExportRegistration(Protocol):
    """
    Declaration of ExportRegistration signature.  Instance of this class
    are returned from RemoteServiceAdmin.export_service to describe the
    exported service.
    """

    def get_export_reference(self) -> Optional["ExportReference"]:
        """
        Get the ExportReference associated with this ExportRegistration.  Will
        be None if this registration has been previously closed.  See
        ExportReference class.

        :return ExportReference associated with this registration, or None
        """
        ...

    def get_export_container_id(self) -> Tuple[str, str]:
        """
        Get the exporting container id of form
        tuple(namespace(string), containerid(string)).
        For example:  ('ecf.namespace.xmlrpc','http://localhost/xml-rpc').
        Will not return None.

        :return: exporting container id of form:
            tuple(namespace(string),containerid(string))
        """
        ...

    def get_remoteservice_id(self) -> Tuple[Tuple[str, str], int]:
        """
        Get the exporting remoteservice id of form:
        tuple(containerid,rsid(int)),
        with containerid of form returned from get_export_container_id.

        For example:
        (('ecf.namespace.xmlrpc','http://localhost/xml-rpc'),1).

        Will not be None.

        :return: exporting remote service id of form: tuple(containerid,rsid(int))
        """
        ...

    def get_reference(self) -> Optional[ServiceReference[Any]]:
        """
        Get the ServiceReference associated with this ExportRegistration.  Will
        be None if the ExportRegistration has been closed, or if an exception
        occurred on attempted export

        :return ServiceReference associated with this ExportRegistration or
        None if this has been previously closed, or if an exception occurred
        on attempted export.
        """
        ...

    def get_exception(self) -> Optional[Tuple[Any, Any, Any]]:
        """
        Get any exception associated with the attempted export.  If not None,
        will be of form:  tuple(exc_type,exc_msg,exc_stack).  For example:
        (SelectContainerException,'No container available',stack_trace).

        :return exception tuple of form: tuple(exc_type,exc_msg,exc_stack) or
        None if no exception occurred during the export associated with this
        ExportRegistration.
        """
        ...

    def get_description(self) -> "EndpointDescription":
        """
        Get EndpointDescription associated with this ExportRegistration.
        Will not be None.  See EndpointDescription class.

        :return EndpointDescription associated with this registration
        """
        ...

    def match_sr(self, svc_ref: ServiceReference[Any], cid: Optional[Tuple[str, str]] = None) -> bool:
        """
        Checks if this export registration matches the given service reference

        :param svc_ref: A service reference
        :param cid: A container ID
        :return: True if the service matches this export registration
        """
        ...

    def update(self, properties: Optional[Dict[str, Any]]) -> Optional["EndpointDescription"]:
        """
        Updates ExportRegistration with new properties.

        :param properties a dictionary of new properties.  May be None.
        :return: EndpointDescription for ExportRegistration, or None if not updated.
        """
        ...

    def close(self) -> None:
        """
        Close this ExportRegistration.  If called after having been previously
        called, will have no effect.
        """
        ...


# ------------------------------------------------------------------------------


class ExportReference(Protocol):
    """
    Declaration of ExportReference signature.  Instance of this class
    are returned from ExportRegistration.get_export_reference().
    See ExportRegistration.get_export_reference or RemoteServiceAdmin.
    get_exported_services.
    """

    def get_export_container_id(self) -> Optional[Tuple[str, str]]:
        """
        Get the exporting container id of form
        tuple(namespace(string),containerid(string)).

        For example:  ('ecf.namespace.xmlrpc','http://localhost/xml-rpc').
        Will be None if this reference has previously been closed.

        :return: exporting container id of form:
            tuple(namespace(string),containerid(string))
        """
        ...

    def get_remoteservice_id(self) -> Optional[Tuple[Tuple[str, str], int]]:
        """
        Get the exporting remoteservice id of form:
        tuple(containerid,rsid(int)), with containerid of form returned
        from get_export_container_id.

        For example:
        (('ecf.namespace.xmlrpc','http://localhost/xml-rpc'),1).

        Will be None if this reference has previously been closed.

        :return: exporting remote service id of form:
            tuple(containerid,rsid(int))
        """
        ...

    def get_reference(self) -> Optional[ServiceReference[Any]]:
        """
        Get the ServiceReference associated with this ExportReference.  Will
        be None if the ExportReference has been closed, or if an exception
        occurred during the attempted export.

        :return: ServiceReference associated with this ExportReference or
        None if this has been previously closed, or if an exception occurred
        during attempted export.
        """
        ...

    def get_description(self) -> Optional["EndpointDescription"]:
        """
        Get EndpointDescription associated with this ExportReference.
        Will not be None.  See EndpointDescription class.  Will be None
        if ExportReference has previously been closed.

        :return: EndpointDescription associated with this reference or
        None if reference has previously been closed.
        """
        ...

    def get_exception(self) -> Optional[Tuple[Any, Any, Any]]:
        """
        Get any exception associated with the attempted export.  If not None,
        will be of form:  tuple(exc_type,exc_msg,exc_stack).  For example:
        (SelectContainerException,'No container available',stack_trace).

        :return: exception tuple of form: tuple(exc_type,exc_msg,exc_stack) or
        None if no exception occurred during the export associated with this
        ExportReference, or if previously closed.
        """
        ...

    def update(self, properties: Dict[str, Any]) -> Optional["EndpointDescription"]:
        """
        Update the service properties of the exported service.

        :param properties: Dictionary of new properties. Should not be None
        :return EndpointDescription associated with existing or None
        if reference previously closed or exception occurred during
        export.
        """
        ...

    def close(self, export_reg: ExportRegistration) -> bool:
        """
        Close this ExportRegistration.  If called after having been previously
        called, will have no effect.
        """
        ...


# ------------------------------------------------------------------------------


class ImportRegistration(Protocol):
    """
    Declaration of ImportRegistration signature.  Instance of this class
    are returned from RemoteServiceAdmin.import_service to allow the
    imported service to be managed.
    """

    def get_import_reference(self) -> "ImportReference":
        """
        Get the ImportReference associated with this ImportRegistration.  Will
        be None if this registration has been previously closed.  See
        ImportReference class.

        :return ImportReference associated with this registration, or None
        """
        ...

    def get_import_container_id(self) -> Tuple[str, str]:
        """
        Get the importing container id of form
        tuple(namespace(string),containerid(string)).

        For example:
        ('ecf.namespace.xmlrpc','123e4567-e89b-42d3-a456-556642440000')

        Will not return None.

        :return: importing container id of form:
            tuple(namespace(string),containerid(string))
        """
        ...

    def get_export_container_id(self) -> Tuple[str, str]:
        """
        Get the exporting container id of form
        tuple(namespace(string),containerid(string)).

        For example:
        ('ecf.namespace.xmlrpc','http://localhost/xml-rpc')

        Will not return None.

        :return: importing container id of form:
            tuple(namespace(string),containerid(string))
        """
        ...

    def get_remoteservice_id(self) -> Tuple[Tuple[str, str], int]:
        """
        Get the exporting remoteservice id of form:
        tuple(containerid,rsid(int)), with containerid of form returned from
        get_export_container_id.

        For example: (('ecf.namespace.xmlrpc','http://localhost/xml-rpc'),1).
        Will not be None.

        :return: exporting remote service id of form:
            tuple(containerid,rsid(int))
        """
        ...

    def get_reference(self) -> Optional[ServiceReference[Any]]:
        """
        Get the ServiceReference associated with this ImportRegistration.
        Will be None if the ImportRegistration has been closed, or if an
        exception occurred on attempted export.

        :return: ServiceReference associated with this ImportRegistration or
        None if this has been previously closed, or if an exception occurred
        on attempted export.
        """
        ...

    def get_exception(self) -> Optional[Tuple[Any, Any, Any]]:
        """
        Get any exception associated with the attempted import.  If not None,
        will be of form:  tuple(exc_type,exc_msg,exc_stack).

        For example:
        (SelectContainerException,'No container available',stack_trace)

        :return: exception tuple of form: tuple(exc_type,exc_msg,exc_stack) or
        None if no exception occurred during the import associated with this
        ImportRegistration.
        """
        ...

    def get_description(self) -> Optional["EndpointDescription"]:
        """
        Get EndpointDescription associated with this ImportRegistration.
        Will not be None.  See EndpointDescription class.

        :return: EndpointDescription associated with this registration
        """
        ...

    def update(self, endpoint_description: "EndpointDescription") -> bool:
        """
        Update the service properties of the imported service.

        :param endpoint_description: EndpointDescription for updated endpoint. Will not be None.
        :return: True if update completed successfully, False if not.
        """
        ...

    def close(self) -> None:
        """
        Close this ImportRegistration.  If called after having been previously
        called, will have no effect.
        """
        ...

    def match_ed(self, ed: "EndpointDescription") -> bool:
        """
        Checks if this registration matches the given endpoint description
        """
        ...


# ------------------------------------------------------------------------------


class ImportReference(Protocol):
    """
    Declaration of ImportReference signature.  Instance of this class
    are returned from ImportRegistration.get_export_reference().
    See ImportRegistration.get_export_reference or RemoteServiceAdmin.
    get_imported_endpoints.
    """

    def get_import_container_id(self) -> Tuple[str, str]:
        """
        Get the importing container id of form
        tuple(namespace(string),containerid(string)).

        For example:
        ('ecf.namespace.xmlrpc','123e4567-e89b-42d3-a456-556642440000')

        Will be None if this reference has previously been closed.

        :return: exporting container id of form:
            tuple(namespace(string),containerid(string))
        """
        ...

    def get_export_container_id(self) -> Tuple[str, str]:
        """
        Get the exporting container id of form
        tuple(namespace(string),containerid(string)).

        For example:
        ('ecf.namespace.xmlrpc','http://localhost/xml-rpc')

        Will be None if this reference has previously been closed.

        :return: exporting container id of form:
            tuple(namespace(string),containerid(string))
        """
        ...

    def get_remoteservice_id(self) -> Tuple[Tuple[str, str], int]:
        """
        Get the importing remoteservice id of form:
        tuple(containerid,rsid(int)), with containerid of form returned from
        get_import_container_id.

        For example:
        (('ecf.namespace.xmlrpc','http://localhost/xml-rpc'),1).

        Will be None if this reference has previously been closed.

        :return: importing remote service id of form:
            tuple(containerid,rsid(int))
        """
        ...

    def get_reference(self) -> Optional[ServiceReference[Any]]:
        """
        Get the ServiceReference of proxy associated with this ImportReference.
        Will be None if the ImportReference has been closed, or if an exception
        occurred during the attempted import.

        :return: ServiceReference associated with this ImportReference or
        None if this has been previously closed, or if an exception occurred
        during attempted export.
        """
        ...

    def get_description(self) -> Optional["EndpointDescription"]:
        """
        Get EndpointDescription associated with this ImportReference.
        Will not be None.  See EndpointDescription class.  Will be None
        if ImportReference has previously been closed.

        :return: EndpointDescription associated with this reference or
        None if reference has previously been closed.
        """
        ...

    def get_exception(self) -> Optional[Tuple[Any, Any, Any]]:
        """
        Get any exception associated with the attempted import.  If not None,
        will be of form:  tuple(exc_type,exc_msg,exc_stack).  For example:
        (SelectContainerException,'No container available',stack_trace).

        :return: exception tuple of form: tuple(exc_type,exc_msg,exc_stack) or
        None if no exception occurred during the import associated with this
        ImportReference, or if previously closed.
        """
        ...

    def update(self, endpoint: "EndpointDescription") -> Optional["EndpointDescription"]:
        """
        Update the service properties of the imported service.

        :param endpoint: Updated description of the endpoint. Should not be None
        :return: EndpointDescription associated with existing or None if
            reference previously closed or exception occurred during import.
        """
        ...

    def close(self, import_reg: ImportRegistration) -> bool:
        """
        Close this ImportReference.  If called after having been previously
        called, will have no effect.
        """
        ...


# ------------------------------------------------------------------------------
# Remote Service Admin Event Listener service specification.  Instances
# of this service are synchronously called by the RemoteServiceAdmin service
# to notify of RemoteServiceAdminEvents.  See RemoteServiceAdminEvent
# class for types of events and data associated with event.  All services
# registered with this service specification will have their remote_admin_event
# method called by RSA after the appropriate event.
SERVICE_RSA_EVENT_LISTENER = "pelix.rsa.remoteserviceadmineventlistener"


@constants.Specification(SERVICE_RSA_EVENT_LISTENER)
class RemoteServiceAdminListener(Protocol):
    """
    Remote service admin listener service interface.  Services
    registered with this as service specification will have this method
    called synchronously by the RSA implementation for notification
    of RSA events.  The event parameter will be of type
    RemoteServiceAdminEvent (see below).
    """

    def remote_admin_event(self, rsa_event: "RemoteServiceAdminEvent") -> None:
        """
        Method called by RSA implementation when RSA events occur.   See
        RemoteServiceAdminEvent above for types of events, and the information
        in each event.

        :param rsa_event the RemoteServiceAdminEvent instance. Will not be None
        """
        ...


# ------------------------------------------------------------------------------
class RemoteServiceAdminEvent:
    """
    Remote service admin event instances are delivered to
    RemoteServiceAdminListener service instances when events of the types
    listed below occur... e.g. IMPORT_REGISTRATION when a successful import
    occurs, EXPORT_REGISTRATION when a successful export occurs, etc.
    """

    IMPORT_REGISTRATION = 1
    EXPORT_REGISTRATION = 2
    EXPORT_UNREGISTRATION = 3
    IMPORT_UNREGISTRATION = 4
    IMPORT_ERROR = 5
    EXPORT_ERROR = 6
    EXPORT_WARNING = 7
    IMPORT_WARNING = 8
    IMPORT_UPDATE = 9
    EXPORT_UPDATE = 10

    @classmethod
    def fromimportreg(cls, bundle: Bundle, import_reg: ImportRegistration) -> "RemoteServiceAdminEvent":
        """
        Creates a RemoteServiceAdminEvent object from an ImportRegistration
        """
        exc = import_reg.get_exception()
        if exc:
            return RemoteServiceAdminEvent(
                RemoteServiceAdminEvent.IMPORT_ERROR,
                bundle,
                import_reg.get_import_container_id(),
                import_reg.get_remoteservice_id(),
                import_reg.get_description(),
                None,
                None,
                exc,
            )

        return RemoteServiceAdminEvent(
            RemoteServiceAdminEvent.IMPORT_REGISTRATION,
            bundle,
            import_reg.get_import_container_id(),
            import_reg.get_remoteservice_id(),
            import_reg.get_description(),
            import_reg.get_import_reference(),
            None,
            None,
        )

    @classmethod
    def fromexportreg(cls, bundle: Bundle, export_reg: ExportRegistration) -> "RemoteServiceAdminEvent":
        """
        Creates a RemoteServiceAdminEvent object from an ExportRegistration
        """
        exc = export_reg.get_exception()
        if exc:
            return RemoteServiceAdminEvent(
                RemoteServiceAdminEvent.EXPORT_ERROR,
                bundle,
                export_reg.get_export_container_id(),
                export_reg.get_remoteservice_id(),
                export_reg.get_description(),
                None,
                None,
                exc,
            )

        return RemoteServiceAdminEvent(
            RemoteServiceAdminEvent.EXPORT_REGISTRATION,
            bundle,
            export_reg.get_export_container_id(),
            export_reg.get_remoteservice_id(),
            export_reg.get_description(),
            None,
            export_reg.get_export_reference(),
            None,
        )

    @classmethod
    def fromexportupdate(cls, bundle: Bundle, export_reg: ExportRegistration) -> "RemoteServiceAdminEvent":
        """
        Creates a RemoteServiceAdminEvent object from the update of an
        ExportRegistration
        """
        exc = export_reg.get_exception()
        if exc:
            return RemoteServiceAdminEvent(
                RemoteServiceAdminEvent.EXPORT_ERROR,
                bundle,
                export_reg.get_export_container_id(),
                export_reg.get_remoteservice_id(),
                export_reg.get_description(),
                None,
                export_reg.get_export_reference(),
                None,
            )

        return RemoteServiceAdminEvent(
            RemoteServiceAdminEvent.EXPORT_UPDATE,
            bundle,
            export_reg.get_export_container_id(),
            export_reg.get_remoteservice_id(),
            export_reg.get_description(),
            None,
            export_reg.get_export_reference(),
            None,
        )

    @classmethod
    def fromimportupdate(cls, bundle: Bundle, import_reg: ImportRegistration) -> "RemoteServiceAdminEvent":
        """
        Creates a RemoteServiceAdminEvent object from the update of an
        ImportRegistration
        """
        exc = import_reg.get_exception()
        if exc:
            return RemoteServiceAdminEvent(
                RemoteServiceAdminEvent.IMPORT_ERROR,
                bundle,
                import_reg.get_import_container_id(),
                import_reg.get_remoteservice_id(),
                import_reg.get_description(),
                None,
                None,
                exc,
            )

        return RemoteServiceAdminEvent(
            RemoteServiceAdminEvent.IMPORT_UPDATE,
            bundle,
            import_reg.get_import_container_id(),
            import_reg.get_remoteservice_id(),
            import_reg.get_description(),
            import_reg.get_import_reference(),
            None,
            None,
        )

    @classmethod
    def fromimportunreg(
        cls,
        bundle: Bundle,
        cid: Tuple[str, str],
        rsid: Tuple[Tuple[str, str], int],
        import_ref: ImportReference,
        exception: Optional[Tuple[Any, Any, Any]],
        endpoint: "EndpointDescription",
    ) -> "RemoteServiceAdminEvent":
        """
        Creates a RemoteServiceAdminEvent object from the departure of an
        ImportRegistration
        """
        return RemoteServiceAdminEvent(
            RemoteServiceAdminEvent.IMPORT_UNREGISTRATION,
            bundle,
            cid,
            rsid,
            endpoint,
            import_ref=import_ref,
            exception=exception,
        )

    @classmethod
    def fromexportunreg(
        cls,
        bundle: Bundle,
        exporterid: Tuple[str, str],
        rsid: Tuple[Tuple[str, str], int],
        export_ref: ExportReference,
        exception: Optional[Tuple[Any, Any, Any]],
        endpoint: "EndpointDescription",
    ) -> "RemoteServiceAdminEvent":
        """
        Creates a RemoteServiceAdminEvent object from the departure of an
        ExportRegistration
        """
        return RemoteServiceAdminEvent(
            RemoteServiceAdminEvent.EXPORT_UNREGISTRATION,
            bundle,
            exporterid,
            rsid,
            endpoint,
            export_ref=export_ref,
            exception=exception,
        )

    @classmethod
    def fromimporterror(
        cls,
        bundle: Bundle,
        importerid: Tuple[str, str],
        rsid: Tuple[Tuple[str, str], int],
        exception: Optional[Tuple[Any, Any, Any]],
        endpoint: "EndpointDescription",
    ) -> "RemoteServiceAdminEvent":
        """
        Creates a RemoteServiceAdminEvent object from an import error
        """
        return RemoteServiceAdminEvent(
            RemoteServiceAdminEvent.IMPORT_ERROR,
            bundle,
            importerid,
            rsid,
            endpoint,
            None,
            None,
            exception,
        )

    @classmethod
    def fromexporterror(
        cls,
        bundle: Bundle,
        exporterid: Tuple[str, str],
        rsid: Tuple[Tuple[str, str], int],
        exception: Optional[Tuple[Any, Any, Any]],
        endpoint: "EndpointDescription",
    ) -> "RemoteServiceAdminEvent":
        """
        Creates a RemoteServiceAdminEvent object from an export error
        """
        return RemoteServiceAdminEvent(
            RemoteServiceAdminEvent.EXPORT_ERROR,
            bundle,
            exporterid,
            rsid,
            endpoint,
            None,
            None,
            exception,
        )

    def __init__(
        self,
        typ: int,
        bundle: Bundle,
        cid: Tuple[str, str],
        rsid: Tuple[Tuple[str, str], int],
        endpoint: Optional["EndpointDescription"],
        import_ref: Optional[ImportReference] = None,
        export_ref: Optional[ExportReference] = None,
        exception: Optional[Tuple[Any, Any, Any]] = None,
    ) -> None:
        self._type = typ
        self._bundle = bundle
        self._cid = cid
        self._rsid = rsid
        self._import_ref = import_ref
        self._export_ref = export_ref
        self._exception = exception
        self._ed = endpoint

    def get_description(self) -> Optional["EndpointDescription"]:
        """
        Get the EndpointDescription associated with this event.
        Will not be None

        :return EndpointDescription associated with this event
        """
        return self._ed

    def get_container_id(self) -> Tuple[str, str]:
        """
        Get the container id of form tuple/2 (namespace,id) where
        both namespace and id are strings. Will not be none.

        :return tuple of namespace,id strings for the Container used
        for export (ExportContainer) or import (ImportContainer).
        """
        return self._cid

    def get_remoteservice_id(self) -> Tuple[Tuple[str, str], int]:
        """
        Get the remote service id of form:  tuple(tuple(namespace,id),rsid)
        where rsid is int and (namespace,id) are as returned from
        get_container_id.  This identifies the *exporting* remote
        service id, so the container id will be the same for
        export and different for import events.

        :return tuple(tuple(namespace,id),rsid) to represent the
        remote service id.
        """
        return self._rsid

    def get_type(self) -> int:
        """
        Get type of RSA event.  Will be one of the constants
        RemoteServiceAdminEvent.IMPORT_REGISTRATION,EXPORT_REGISTRATION, etc.

        :return rsa event type (int)
        """
        return self._type

    def get_source(self) -> Bundle:
        """
        Get the Bundle source for this event.  Will usually be
        the pelix.rsa.remoteserviceadmin event.  Will not be
        None.

        :return source bundle for this event.
        """
        return self._bundle

    def get_import_ref(self) -> Optional[ImportReference]:
        """
        Get ImportReference instance associated with this event.
        Will be None if type is IMPORT_*.

        :return import reference associated with this event
        """
        return self._import_ref

    def get_export_ref(self) -> Optional[ExportReference]:
        """
        Get ExportReference instance associated with this event.
        Will be None if type is EXPORT_*.

        :return export reference associated with this event
        """
        return self._export_ref

    def get_exception(self) -> Optional[Tuple[Any, Any, Any]]:
        """
        Get exception in tuple(exc_type,exc_name,traceback) form.
        If None, no exception occurred in RSA import/export. If
        not None, then an exception occurred and the EVENT_TYPE will
        be *ERROR
        """
        return self._exception


def create_uuid() -> str:
    """
    Generates a UUID 4

    :return: A string UUID
    """
    return str(uuid.uuid4())


def create_uuid_uri() -> str:
    """
    Generates a UUID URI

    :return: A uuid:<uuid> string
    """
    return "uuid:" + create_uuid()


def time_since_epoch() -> int:
    """
    Gives a timestamp floored to last second
    """
    return int(time.time() - 1000)


def get_fw_uuid(context: BundleContext) -> str:
    """
    Returns the framework UUID

    :param context: The bundle context
    :return: The framework UUID
    """
    return str(context.get_property(constants.OSGI_FRAMEWORK_UUID))


def get_matching_interfaces(
    object_class: List[str], exported_intfs: Optional[List[str]]
) -> Optional[List[str]]:
    """
    Returns the list of interfaces matching the export property

    :param object_class: The specifications of the service
    :param exported_intfs: The declared exported interfaces
    :return: The list of declared exported interfaces
    """
    if not object_class or not exported_intfs:
        return None

    if isinstance(exported_intfs, str) and exported_intfs == "*":
        return object_class

    # after this exported_intfs will be list
    exported_intfs = get_string_plus_property_value(exported_intfs)
    if not exported_intfs:
        return None

    if len(exported_intfs) == 1 and exported_intfs[0] == "*":
        return object_class

    return exported_intfs


def get_prop_value(name: str, props: Optional[Dict[str, Any]], default: Any = None) -> Any:
    """
    Returns the value of a property or the default one

    :param name: Name of a property
    :param props: Dictionary of properties
    :param default: Default value
    :return: The value of the property or the default one
    """
    if not props:
        return default

    try:
        return props[name]
    except KeyError:
        return default


def set_prop_if_null(name: str, props: Dict[str, Any], if_null: Any) -> None:
    """
    Updates the value of a property if the previous one was None

    :param name: Name of the property
    :param props: Dictionary of properties
    :param if_null: Value to insert if the previous was None
    """
    value = get_prop_value(name, props)
    if value is None:
        props[name] = if_null


def get_string_plus_property_value(value: Any) -> Optional[List[str]]:
    """
    Converts a string or list of string into a list of strings

    :param value: A string or a list of strings
    :return: A list of strings or None
    """
    if value:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)

    return None


def convert_string_plus_value(values: List[str]) -> Union[None, str, List[str]]:
    """
    Normalizes a list of string

    :param values: A list of strings
    :return: None, a single string or a list of strings
    """
    if not values:
        return None

    if len(values) == 1:
        return values[0]

    return values


def parse_string_plus_value(value: str) -> List[str]:
    """
    Parses a comma-separated value

    :param value: A string representation of a list
    :return: A list of strings
    """
    return value.split(",")


def get_string_plus_property(
    name: str, props: Dict[str, Any], default: Optional[List[str]] = None
) -> Optional[List[str]]:
    """
    Returns the value of the given property or the default value

    :param name: A property name
    :param props: A dictionary of properties
    :param default: Value to return if the property doesn't exist
    :return: The property value or the default one
    """
    val = get_string_plus_property_value(get_prop_value(name, props, default))
    return default if val is None else val


def get_current_time_millis() -> int:
    """
    Gets the current time stamp in milliseconds

    :return: The current time stamp
    """
    return int(time.time() * 1000)


def get_exported_interfaces(
    svc_ref: ServiceReference[Any], overriding_props: Optional[Dict[str, Any]] = None
) -> Optional[List[str]]:
    """
    Looks for the interfaces exported by a service

    :param svc_ref: Service reference
    :param overriding_props: Properties overriding service ones
    :return: The list of exported interfaces
    """
    # first check overriding_props for service.exported.interfaces
    exported_intfs = cast(Optional[List[str]], get_prop_value(SERVICE_EXPORTED_INTERFACES, overriding_props))
    # then check svc_ref property
    if not exported_intfs:
        exported_intfs = svc_ref.get_property(SERVICE_EXPORTED_INTERFACES)

    if not exported_intfs:
        return None

    return get_matching_interfaces(svc_ref.get_property(constants.OBJECTCLASS), exported_intfs)


def validate_exported_interfaces(object_class: List[str], exported_intfs: Optional[List[str]]) -> bool:
    """
    Validates that the exported interfaces are all provided by the service

    :param object_class: The specifications of a service
    :param exported_intfs: The exported specifications
    :return: True if the exported specifications are all provided by the service
    """
    if not exported_intfs or not isinstance(exported_intfs, list) or not exported_intfs:
        return False
    else:
        for exintf in exported_intfs:
            if exintf not in object_class:
                return False
    return True


def get_package_from_classname(class_name: str) -> Optional[str]:
    """
    Returns the name of the package declaring the given class

    :param class_name: A full class name
    :return: The name of a package or None
    """
    try:
        return class_name[: class_name.rindex(".")]
    except ValueError:
        return None


def get_package_versions(intfs: List[str], props: Dict[str, Any]) -> List[Tuple[str, str]]:
    """
    Gets the package version of interfaces

    :param intfs: A list of interfaces
    :param props: A dictionary containing endpoint package versions
    :return: A list of tuples (package name, version)
    """
    result = []
    for intf in intfs:
        pkg_name = get_package_from_classname(intf)
        if pkg_name:
            key = ENDPOINT_PACKAGE_VERSION_ + pkg_name
            val = props.get(key, None)
            if val:
                result.append((key, val))
    return result


_NEXT_RSID = 1
_NEXT_RSID_LOCK = threading.Lock()


def get_next_rsid() -> int:
    """
    Gets the next RS ID and increments the counter

    :return: The next RS ID
    """
    global _NEXT_RSID
    with _NEXT_RSID_LOCK:
        new_rsid = _NEXT_RSID
        _NEXT_RSID += 1
        return new_rsid


def copy_ref_props(service_ref: ServiceReference[Any]) -> Dict[str, Any]:
    """
    Copies the properties of a service reference

    :param service_ref: A service reference
    :return: A copy of properties of the service
    """
    return service_ref.get_properties().copy()


def merge_dicts(*dict_args: Dict[K, Any]) -> Dict[K, Any]:
    """
    Given any number of dicts, shallow copy and merge into a new dict,
    precedence goes to key value pairs in latter dicts.
    """
    result = {}
    for dictionary in dict_args:
        result.update(dictionary)
    return result


def merge_overriding_props(
    service_ref: ServiceReference[Any], overriding_props: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Overrides the properties of the service with the given ones

    :param service_ref: A service reference
    :param overriding_props: Properties overriding the service ones
    :return: The merged properties dictionary
    """
    ref_props = copy_ref_props(service_ref)
    return merge_dicts(ref_props, overriding_props)


def get_rsa_props(
    object_class: List[str],
    exported_cfgs: Optional[List[str]],
    remote_intents: Optional[List[str]] = None,
    ep_svc_id: Optional[int] = None,
    fw_id: Optional[str] = None,
    pkg_vers: Union[None, Tuple[str, str], List[Tuple[str, str]]] = None,
    service_intents: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Constructs a dictionary of RSA properties from the given arguments

    :param object_class: Service specifications
    :param exported_cfgs: Export configurations
    :param remote_intents: Supported remote intents
    :param ep_svc_id: Endpoint service ID
    :param fw_id: Remote Framework ID
    :param pkg_vers: Version number of the specification package
    :param service_intents: Service intents
    :return: A dictionary of properties
    """
    results: Dict[str, Any] = {}
    if not object_class:
        raise Exception("object_class must be an [] of Strings")
    results["objectClass"] = object_class
    if not exported_cfgs:
        raise Exception("exported_cfgs must be an array of Strings")
    results[REMOTE_CONFIGS_SUPPORTED] = exported_cfgs
    results[SERVICE_IMPORTED_CONFIGS] = exported_cfgs
    if remote_intents:
        results[REMOTE_INTENTS_SUPPORTED] = remote_intents
    if service_intents:
        results[SERVICE_INTENTS] = service_intents
    if not ep_svc_id:
        ep_svc_id = get_next_rsid()
    results[ENDPOINT_SERVICE_ID] = ep_svc_id
    results[SERVICE_ID] = ep_svc_id
    if not fw_id:
        # No framework ID means an error
        fw_id = "endpoint-in-error"
    results[ENDPOINT_FRAMEWORK_UUID] = fw_id
    if pkg_vers:
        if isinstance(pkg_vers, tuple):
            results[pkg_vers[0]] = pkg_vers[1]
        else:
            for pkg_ver in pkg_vers:
                results[pkg_ver[0]] = pkg_ver[1]
    results[ENDPOINT_ID] = create_uuid()
    results[SERVICE_IMPORTED] = "true"
    return results


def get_ecf_props(
    ep_id: str,
    ep_id_ns: str,
    rsvc_id: Optional[int] = None,
    ep_ts: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Prepares the ECF properties

    :param ep_id: Endpoint ID, error if None
    :param ep_id_ns: Namespace of the Endpoint ID, error if None
    :param rsvc_id: Remote service ID
    :param ep_ts: Timestamp of the endpoint
    :return: A dictionary of ECF properties
    """
    results: Dict[str, Any] = {}
    if not ep_id:
        raise Exception("ep_id must be a valid endpoint id")
    results[ECF_ENDPOINT_ID] = ep_id
    if not ep_id_ns:
        raise Exception("ep_id_ns must be a valid namespace")
    results[ECF_ENDPOINT_CONTAINERID_NAMESPACE] = ep_id_ns
    if not rsvc_id:
        rsvc_id = get_next_rsid()
    results[ECF_RSVC_ID] = rsvc_id
    if not ep_ts:
        ep_ts = time_since_epoch()
    results[ECF_ENDPOINT_TIMESTAMP] = ep_ts
    return results


def get_extra_props(props: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns the extra properties, *i.e.* non-ECF, non-RSA properties

    :param props: A dictionary of properties
    :return: A filtered dictionary
    """
    return {
        key: value
        for key, value in props.items()
        if key not in ECFPROPNAMES
        and key not in RSA_PROP_NAMES
        and not key.startswith(ENDPOINT_PACKAGE_VERSION_)
    }


def get_edef_props(
    object_class: List[str],
    exported_cfgs: Optional[List[str]],
    ep_namespace: str,
    ep_id: str,
    ecf_ep_id: str,
    ep_rsvc_id: int,
    ep_ts: int,
    remote_intents: Optional[List[str]] = None,
    fw_id: Optional[str] = None,
    pkg_ver: Union[None, Tuple[str, str], List[Tuple[str, str]]] = None,
    service_intents: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Prepares the EDEF properties of an endpoint, merge of RSA and ECF
    properties
    """
    osgi_props = get_rsa_props(
        object_class,
        exported_cfgs,
        remote_intents,
        ep_rsvc_id,
        fw_id,
        pkg_ver,
        service_intents,
    )
    ecf_props = get_ecf_props(ecf_ep_id, ep_namespace, ep_rsvc_id, ep_ts)
    return merge_dicts(osgi_props, ecf_props)


def get_edef_props_error(object_class: List[str]) -> Dict[str, Any]:
    """
    Returns the EDEF properties for an errorred endpoint
    """
    return get_edef_props(
        object_class,
        ERROR_IMPORTED_CONFIGS,
        ERROR_NAMESPACE,
        ERROR_EP_ID,
        ERROR_ECF_EP_ID,
        0,
        0,
    )


def get_dot_properties(prefix: str, props: Dict[str, Any], remove_prefix: bool) -> Dict[str, Any]:
    """
    Gets the properties starting with the given prefix
    """
    result_props = {}
    if props:
        dot_keys = [x for x in props.keys() if x.startswith(prefix + ".")]
        for dot_key in dot_keys:
            if remove_prefix:
                new_key = dot_key[len(prefix) + 1 :]
            else:
                new_key = dot_key
            result_props[new_key] = props.get(dot_key)
    return result_props


def is_reserved_property(key: str) -> bool:
    """
    Tests if the given property key is reserved

    Reserved keys are:
    * RSA property names
    * ECF property names
    * Property names starting with a dot (``.``)

    :param key: A property name
    :return: True if the property is reserved
    """
    return key in RSA_PROP_NAMES or key in ECFPROPNAMES or key.startswith(".")


def remove_from_props(props: Dict[str, Any], keys: Iterable[str]) -> Dict[str, Any]:
    """
    Removes in-place the given keys from the properties

    :param props: A dictionary of properties
    :param keys: The keys to remove
    :return: The given dictionary of properties
    """
    for key in keys:
        try:
            del props[key]
        except KeyError:
            pass
    return props


def copy_non_reserved(props: Dict[str, Any], target: Dict[str, Any]) -> Dict[str, Any]:
    """
    Copies all properties with non-reserved names from ``props`` to ``target``

    :param props: A dictionary of properties
    :param target: Another dictionary
    :return: The target dictionary
    """
    target.update({key: value for key, value in props.items() if not is_reserved_property(key)})
    return target


def copy_non_ecf(props: Dict[str, Any], target: Dict[str, Any]) -> Dict[str, Any]:
    """
    Copies non-ECF properties from ``props`` to ``target``

    :param props: An input dictionary
    :param target: The dictionary to copy non-ECF properties to
    :return: The ``target`` dictionary
    """
    target.update({key: value for key, value in props.items() if key not in ECFPROPNAMES})
    return target


def set_append(input_set: Set[T], item: Union[None, T, Iterable[T]]) -> Set[T]:
    """
    Appends in-place the given item to the set.
    If the item is a list, all elements are added to the set.

    :param input_set: An existing set
    :param item: The item or list of items to add
    :return: The given set
    """
    if item:
        if isinstance(item, collections.abc.Iterable):
            input_set.update(item)
        else:
            input_set.add(item)
    return input_set


def cid_to_string(cid: Tuple[str, str]) -> str:
    """
    Converts the Container ID to a string

    :param cid: A Container ID tuple
    :return: The Container ID as a string
    """
    return cid[1]


def rsid_to_string(rsid: Tuple[Tuple[str, str], int]) -> str:
    """
    Converts the RS ID tuple to a string

    :param rsid: An RS ID tuple
    :return: The RS ID as a string
    """
    return "{0}:{1}".format(cid_to_string(rsid[0]), rsid[1])


def prop_dot_suffix(prop_name: str, suffix: Optional[str] = None) -> str:
    """
    Joins both strings with a dot (".")
    """
    if not suffix:
        suffix = ""
    return f"{prop_name}.{suffix}"


# ------------------------------------------------------------------------------
# Exception classes


class SelectExporterError(Exception):
    """
    Error selecting exporter
    """

    ...


class SelectImporterError(Exception):
    """
    Error selecting importer
    """

    ...


class RemoteServiceError(Exception):
    """
    Generic RSA exception
    """

    ...
