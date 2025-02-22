#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix Remote Services: Java-compatible RPC, based on the Jabsorb library

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
from typing import Any, Callable, Dict, Iterable, Optional, Union

import jsonrpclib.jsonrpc as jsonrpclib
from jsonrpclib.SimpleJSONRPCServer import NoMulticallResult, SimpleJSONRPCDispatcher

import pelix.http
import pelix.misc.jabsorb as jabsorb
import pelix.remote
import pelix.remote.transport.commons as commons
from pelix.framework import BundleContext
from pelix.internals.registry import ServiceReference
from pelix.ipopo.decorators import ComponentFactory, Invalidate, Property, Provides, Requires, Validate
from pelix.remote.beans import ImportEndpoint
from pelix.utilities import to_str

# ------------------------------------------------------------------------------

# Documentation strings format
__docformat__ = "restructuredtext en"

# Module version
__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------

JABSORB_CONFIG = "ecf.jabsorb"
""" Remote Service configuration constant """

PROP_JABSORB_ENDPOINT_NAME = f"{JABSORB_CONFIG}.name"
""" Name of the endpoint """

PROP_HTTP_ACCESSES = f"{JABSORB_CONFIG}.accesses"
""" HTTP accesses (comma-separated String) """

HOST_SERVLET_PATH = "/JABSORB-RPC"
""" Default servlet path """

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


class _JabsorbRpcServlet(SimpleJSONRPCDispatcher):
    """
    A JSON-RPC servlet, replacing the SimpleJSONRPCDispatcher from jsonrpclib,
    converting data from and to Jabsorb format.
    """

    def __init__(
        self,
        dispatch_method: Callable[[str, Union[Iterable[Any], Dict[str, Any]]], Any],
        encoding: Optional[str] = None,
    ) -> None:
        """
        Sets up the servlet
        """
        SimpleJSONRPCDispatcher.__init__(self, encoding)

        # Register the system.* functions
        self.register_introspection_functions()

        # Make a link to the dispatch method
        self._dispatch_method = dispatch_method

    def _simple_dispatch(self, name: str, params: Union[Iterable[Any], Dict[str, Any]]) -> Any:
        """
        Dispatch method
        """
        try:
            # Internal method
            func = self.funcs[name]
        except KeyError:
            # Other method
            pass
        else:
            # Internal method found
            if isinstance(params, (list, tuple)):
                return func(*params)

            return func(**params)

        # Avoid calling this method in the "except" block, as it would be in
        # an exception state (logs will consider the KeyError as a failure)
        return self._dispatch_method(name, params)

    def do_POST(
        self, request: pelix.http.AbstractHTTPServletRequest, response: pelix.http.AbstractHTTPServletResponse
    ) -> None:
        # pylint: disable=C0103
        """
        Handle a POST request

        :param request: The HTTP request bean
        :param response: The HTTP response handler
        """
        # Get the request JSON content
        data = jsonrpclib.loads(to_str(request.read_data()))

        # Convert from Jabsorb
        data = jabsorb.from_jabsorb(data)

        # Dispatch
        result: Any
        try:
            result = self._unmarshaled_dispatch(data, self._simple_dispatch)
        except NoMulticallResult:
            # No result (never happens, but who knows...)
            result = None

        if result is not None:
            # Convert result to Jabsorb
            if "result" in result:
                result["result"] = jabsorb.to_jabsorb(result["result"])

            # Store JSON
            result = jsonrpclib.jdumps(result)
        else:
            # It was a notification
            result = ""

        # Send the result
        response.send_content(200, result, "application/json-rpc")


# ------------------------------------------------------------------------------


@ComponentFactory(pelix.remote.FACTORY_TRANSPORT_JABSORBRPC_EXPORTER)
@Provides(pelix.remote.RemoteServiceExportProvider)
@Requires("_http", pelix.http.HTTPService)
@Property("_path", pelix.http.HTTP_SERVLET_PATH, HOST_SERVLET_PATH)
@Property(
    "_kinds",
    pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED,
    (JABSORB_CONFIG, "jabsorb-rpc"),
)
class JabsorbRpcServiceExporter(commons.AbstractRpcServiceExporter):
    """
    JABSORB-RPC Remote Services exporter
    """

    _http: pelix.http.HTTPService

    def __init__(self) -> None:
        """
        Sets up the exporter
        """
        # Call parent
        super(JabsorbRpcServiceExporter, self).__init__()

        # HTTP Service
        self._path = ""

        # JSON-RPC servlet
        self._servlet: Optional[pelix.http.Servlet] = None

    def make_endpoint_properties(
        self, svc_ref: ServiceReference[Any], name: str, fw_uid: Optional[str]
    ) -> Dict[str, Any]:
        """
        Prepare properties for the ExportEndpoint to be created

        :param svc_ref: Service reference
        :param name: Endpoint name
        :param fw_uid: Framework UID
        :return: A dictionary of extra endpoint properties
        """
        # Get the Jabsorb-RPC endpoint name
        jabsorb_name = svc_ref.get_property(PROP_JABSORB_ENDPOINT_NAME)
        if jabsorb_name:
            # The end point name has been configured in the Jabsorb way
            name = jabsorb_name

        return {
            pelix.remote.PROP_ENDPOINT_NAME: name,
            # Jabsorb-RPC endpoint name
            PROP_JABSORB_ENDPOINT_NAME: name,
            # HTTP accesses, as a comma-separated string
            PROP_HTTP_ACCESSES: self.get_accesses(),
        }

    def get_accesses(self) -> str:
        """
        Retrieves the URLs to access this component as a comma-separated list.
        The first URL contains a '{server}' variable
        """
        # Get HTTP server access
        host, port = self._http.get_access()
        if ":" in host:
            # IPv6 address
            host = f"[{host}]"

        # Return two accesses: with a {server} variable and with the
        # bound address
        model = "http{2}://{{server}}:{0}{1}".format(port, self._path, "s" if self._http.is_https() else "")
        return ",".join((model, model.format(server=host)))

    @Validate
    def validate(self, context: BundleContext) -> None:
        """
        Component validated
        """
        # Call parent
        super(JabsorbRpcServiceExporter, self).validate(context)

        # Create/register the servlet
        self._servlet = _JabsorbRpcServlet(self.dispatch)
        self._path = self._path or ""
        self._http.register_servlet(self._path, self._servlet)

    @Invalidate
    def invalidate(self, context: BundleContext) -> None:
        """
        Component invalidated
        """
        # Unregister the servlet
        self._http.unregister(None, self._servlet)

        # Call parent
        super(JabsorbRpcServiceExporter, self).invalidate(context)

        # Clean up members
        self._servlet = None


# ------------------------------------------------------------------------------


class _ServiceCallProxy:
    # pylint: disable=R0903
    """
    Service call proxy
    """

    def __init__(self, name: str, url: str) -> None:
        """
        Sets up the call proxy

        :param name: End point name
        :param url: End point URL
        """
        self.__name = name
        self.__url = url

    def __getattr__(self, name: str) -> Any:
        """
        Prefixes the requested attribute name by the endpoint name
        """
        # Make a proxy for this call
        # This is an ugly trick to handle multithreaded calls, as the
        # underlying proxy re-uses the same connection when possible: sometimes
        # it means sending a request before retrieving a result
        proxy = jsonrpclib.ServerProxy(self.__url)

        def wrapped_call(*args: Any, **kwargs: Any) -> Any:
            """
            Wrapped call
            """
            # Get the method from the proxy
            method = getattr(proxy, f"{self.__name}.{name}")

            # Convert arguments
            args = tuple(jabsorb.to_jabsorb(arg) for arg in args)
            kwargs = {key: jabsorb.to_jabsorb(value) for key, value in kwargs.items()}

            result = method(*args, **kwargs)
            return jabsorb.from_jabsorb(result)

        return wrapped_call


# ------------------------------------------------------------------------------


@ComponentFactory(pelix.remote.FACTORY_TRANSPORT_JABSORBRPC_IMPORTER)
@Provides(pelix.remote.RemoteServiceImportEndpointListener)
@Property(
    "_kinds",
    pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED,
    (JABSORB_CONFIG, "jabsorb-rpc"),
)
class JabsorbRpcServiceImporter(commons.AbstractRpcServiceImporter):
    """
    JABSORB-RPC Remote Services importer
    """

    def make_service_proxy(self, endpoint: ImportEndpoint) -> Any:
        """
        Creates the proxy for the given ImportEndpoint

        :param endpoint: An ImportEndpoint bean
        :return: A service proxy
        """
        # Get the access URL
        access_url = endpoint.properties.get(PROP_HTTP_ACCESSES)
        if not access_url:
            # No URL information
            _logger.warning("No access URL given: %s", endpoint)
            return None

        # Get the first URL in the list
        access_url = access_url.split(",")[0]

        if endpoint.server is not None:
            # Server information given
            access_url = access_url.format(server=endpoint.server)
        else:
            # Use the local IP as the source server, just in case
            local_server = "localhost"
            access_url = access_url.format(server=local_server)

        # Compute the name
        name = endpoint.properties.get(PROP_JABSORB_ENDPOINT_NAME)
        if not name:
            _logger.error("Remote endpoint has no name: %s", endpoint)
            return None

        # Prepare the proxy
        return _ServiceCallProxy(name, access_url)

    def clear_service_proxy(self, endpoint: ImportEndpoint) -> None:
        """
        Destroys the proxy made for the given ImportEndpoint

        :param endpoint: An ImportEndpoint bean
        """
        # Nothing to do
        return
