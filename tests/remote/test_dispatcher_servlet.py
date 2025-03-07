#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the Remote Services Exports Dispatcher

:author: Thomas Calmant
"""

import http.client as httplib
import json
import unittest
import uuid
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import pelix.constants
import pelix.framework
import pelix.remote
import pelix.remote.beans as beans
from pelix.http import AbstractHTTPServletRequest, AbstractHTTPServletResponse
from pelix.internals.registry import ServiceReference
from pelix.ipopo.constants import use_ipopo
from pelix.utilities import to_str

# ------------------------------------------------------------------------------

__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class Exporter:
    """
    Service exporter
    """

    def __init__(self, context: pelix.framework.BundleContext) -> None:
        """
        Sets up members
        """
        self.context = context
        self.configs: List[str] = ["test.config"]
        self.endpoints: List[beans.ExportEndpoint] = []

    def export_service(self, svc_ref: ServiceReference[Any], name: str, fw_uid: str) -> beans.ExportEndpoint:
        """
        Endpoint registered
        """
        service = self.context.get_service(svc_ref)
        endpoint = beans.ExportEndpoint(str(uuid.uuid4()), fw_uid, self.configs, name, svc_ref, service, {})
        self.endpoints.append(endpoint)
        return endpoint

    def update_export(
        self, endpoint: beans.ExportEndpoint, new_name: str, old_properties: Dict[str, Any]
    ) -> None:
        """
        Endpoint updated
        """
        pass

    def unexport_service(self, endpoint: beans.ExportEndpoint) -> None:
        """
        Endpoint removed
        """
        self.endpoints.remove(endpoint)


class ImportListener:
    """
    Imports listener
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        self.endpoints: Dict[str, beans.ImportEndpoint] = {}

    def endpoint_added(self, endpoint: beans.ImportEndpoint) -> None:
        """
        Endpoint registered
        """
        self.endpoints[endpoint.uid] = endpoint

    def endpoint_updated(self, endpoint: beans.ImportEndpoint, properties: Dict[str, Any]) -> None:
        """
        Endpoint updated
        """
        pass

    def endpoint_removed(self, uid: str) -> None:
        """
        Endpoint removed
        """
        del self.endpoints[uid]


class FakeSerlvet:
    """
    Fake servlet to grab POST data
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        self.data: Optional[str] = None
        self.error: bool = False

    def do_POST(self, request: AbstractHTTPServletRequest, response: AbstractHTTPServletResponse) -> None:
        """
        Handles a POST request

        :param request: Request handler
        :param response: Response handler
        """
        # Store data
        self.data = to_str(request.read_data())

        # Respond
        if self.error:
            response.send_content(404, "Not active", "text/plain")
        else:
            response.send_content(200, "OK", "text/plain")


# ------------------------------------------------------------------------------


class DispatcherTest(unittest.TestCase):
    """
    Tests for the Remote Services dispatcher
    """

    framework: pelix.framework.Framework
    servlet: pelix.remote.RemoteServiceDispatcherServlet

    def setUp(self) -> None:
        """
        Sets up the test
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(
            ("pelix.ipopo.core", "pelix.http.basic", "pelix.remote.dispatcher", "pelix.remote.registry")
        )
        self.framework.start()

        # Instantiate components
        context = self.framework.get_bundle_context()
        with use_ipopo(context) as ipopo:
            # Instantiate remote service components
            # ... HTTP server
            http = ipopo.instantiate(
                "pelix.http.service.basic.factory", "http-server", {"pelix.http.port": 0}
            )

            # ... servlet giving access to the registry
            self.servlet = ipopo.instantiate(
                pelix.remote.FACTORY_REGISTRY_SERVLET, "pelix-remote-dispatcher-servlet"
            )

        # Keep the HTTP server port
        self.port = http.get_access()[1]
        self.servlet_path = self.servlet.get_access()[1]

        # Get the framework UID
        self.framework_uid = context.get_property(pelix.constants.FRAMEWORK_UID)

        # Get the service
        svc_ref = context.get_service_reference(pelix.remote.RemoteServiceDispatcher)
        assert svc_ref is not None
        self.dispatcher = context.get_service(svc_ref)

    def tearDown(self) -> None:
        """
        Cleans up for next test
        """
        # Stop the framework
        pelix.framework.FrameworkFactory.delete_framework()

        self.framework = None  # type: ignore
        self.dispatcher = None  # type: ignore

    def _http_get(self, path: str) -> Tuple[int, str]:
        """
        Makes a HTTP GET request to the given path and returns the response
        as a string

        :param path: Sub path for the dispatcher servlet
        :return: A (status, response string) tuple
        """
        # Prepare the request path
        if path[0] == "/":
            path = path[1:]
        path = urljoin(self.servlet_path, path)

        # Request the end points
        conn = httplib.HTTPConnection("localhost", self.port)
        conn.request("GET", path)
        result = conn.getresponse()
        data = result.read()
        conn.close()

        # Convert the response to a string
        return result.status, to_str(data)

    def _http_post(self, path: str, body: str) -> Tuple[int, str]:
        """
        Makes a HTTP GET request to the given path and returns the response
        as a string

        :param path: Sub path for the dispatcher servlet
        :return: A (status, response string) tuple
        """
        # Prepare the request path
        if path[0] == "/":
            path = path[1:]
        path = urljoin(self.servlet_path, path)

        # Request the end points
        conn = httplib.HTTPConnection("localhost", self.port)
        conn.request("POST", path, body, {"Content-Type": "application/json"})
        result = conn.getresponse()
        data = result.read()
        conn.close()

        # Convert the response to a string
        return result.status, to_str(data)

    def testInvalidPath(self) -> None:
        """
        Tests the behavior of the servlet on an invalid path
        """
        status, _ = self._http_get("invalid_path")
        self.assertEqual(status, 404)

    def testGetFrameworkUid(self) -> None:
        """
        Tests the framework UID request
        """
        # Request dispatcher framework UID
        status, response = self._http_get("/framework")

        # Check result
        self.assertEqual(status, 200)
        self.assertEqual(response, json.dumps(self.framework_uid))

    def testListEndpoints(self) -> None:
        """
        Checks if the list of endpoints is correctly given
        """
        # Register an exporter
        context = self.framework.get_bundle_context()
        exporter = Exporter(context)
        context.register_service(pelix.remote.SERVICE_EXPORT_PROVIDER, exporter, {})

        # Empty list
        status, response = self._http_get("/endpoints")

        # Check result
        self.assertEqual(status, 200)
        self.assertListEqual(json.loads(response), [])

        # Register some endpoints
        svc_regs = []
        for _ in range(3):
            # Register a service
            svc_regs.append(
                context.register_service(
                    "sample.spec", object(), {pelix.remote.PROP_EXPORTED_INTERFACES: "*"}
                )
            )

            # Request the list of endpoints
            status, response = self._http_get("/endpoints")

            # Check result
            self.assertEqual(status, 200)

            # Get all endpoints ID
            data = json.loads(response)
            local_uids = [endpoint.uid for endpoint in exporter.endpoints]
            servlet_uids = [item["uid"] for item in data]

            self.assertCountEqual(servlet_uids, local_uids)

        # Unregister them
        for svc_reg in svc_regs:
            # Unregister the service
            svc_reg.unregister()

            # Request the list of endpoints
            status, response = self._http_get("/endpoints")

            # Check result
            self.assertEqual(status, 200)

            # Get all endpoints ID
            data = json.loads(response)
            local_uids = [endpoint.uid for endpoint in exporter.endpoints]
            servlet_uids = [item["uid"] for item in data]

            self.assertCountEqual(servlet_uids, local_uids)

    def testEndpoint(self) -> None:
        """
        Checks the details of an endpoint
        """
        # Register an exporter
        context = self.framework.get_bundle_context()
        exporter = Exporter(context)
        context.register_service(pelix.remote.SERVICE_EXPORT_PROVIDER, exporter, {})

        # With no UID given
        status, _ = self._http_get("/endpoint")

        # Check result
        self.assertEqual(status, 404)

        # Register a service
        svc_reg = context.register_service(
            "sample.spec", object(), {pelix.remote.PROP_EXPORTED_INTERFACES: "*"}
        )

        # Get the endpoint bean
        endpoint = exporter.endpoints[-1]

        # Request the details of the endpoint
        status, response = self._http_get("/endpoint/{0}".format(endpoint.uid))

        # Check result
        self.assertEqual(status, 200)

        # Check the content
        data = json.loads(response)
        for key, attr in (("uid", "uid"), ("sender", "framework"), ("name", "name")):
            self.assertEqual(data[key], getattr(endpoint, attr))

        # Unregister it
        svc_reg.unregister()

        # Request the list of endpoints
        status, _ = self._http_get("/endpoint/{0}".format(endpoint.uid))

        # Check result
        self.assertEqual(status, 404)

    def testGrabEndpoint(self) -> None:
        """
        Tests the grab_endpoint method
        """
        # Register an exporter
        context = self.framework.get_bundle_context()
        exporter = Exporter(context)
        context.register_service(pelix.remote.SERVICE_EXPORT_PROVIDER, exporter, {})

        # Register a service
        svc_reg = context.register_service(
            "sample.spec", object(), {pelix.remote.PROP_EXPORTED_INTERFACES: "*"}
        )

        # Get the endpoint bean
        endpoint = exporter.endpoints[-1]

        # Tell the servlet to get this endpoint
        grabbed_endpoint = self.servlet.grab_endpoint("localhost", self.port, self.servlet_path, endpoint.uid)

        # Check endpoint values
        assert grabbed_endpoint is not None
        self.assertIsNot(grabbed_endpoint, endpoint)
        self.assertEqual(grabbed_endpoint.uid, endpoint.uid)
        self.assertEqual(grabbed_endpoint.framework, endpoint.framework)

        # Properties will be different
        # Specifications might be prefixed with the language
        self.assertGreaterEqual(len(grabbed_endpoint.specifications), 1)
        self.assertEqual(len(grabbed_endpoint.specifications), len(endpoint.specifications))
        for grabbed, exported in zip(grabbed_endpoint.specifications, grabbed_endpoint.specifications):
            self.assertIn(exported, grabbed)

        # Unregister the service
        svc_reg.unregister()

        # Check the result
        self.assertIsNone(self.servlet.grab_endpoint("localhost", self.port, self.servlet_path, endpoint.uid))

        # Test on an invalid host/port
        self.assertIsNone(self.servlet.grab_endpoint("localhost", -1, self.servlet_path, endpoint.uid))

    def testInvalidPostPath(self) -> None:
        """
        Tries to send a POST request to an invalid path
        """
        for path in ("framework", "endpoint", "invalid"):
            status, _ = self._http_post(path, "some-data")
            self.assertEqual(status, 404)

    def testPostEndpoints(self) -> None:
        """
        Tests the POST of endpoints
        """
        # Register an exporter
        context = self.framework.get_bundle_context()
        exporter = Exporter(context)
        context.register_service(pelix.remote.SERVICE_EXPORT_PROVIDER, exporter, {})

        # Register an importer
        importer = ImportListener()
        context.register_service(
            pelix.remote.SERVICE_IMPORT_ENDPOINT_LISTENER,
            importer,
            {pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED: exporter.configs[0]},
        )

        # Register a service
        context.register_service("sample.spec", object(), {pelix.remote.PROP_EXPORTED_INTERFACES: "*"})

        # Get the endpoint bean
        endpoint = exporter.endpoints[-1]

        # Get its representation
        status, response = self._http_get("/endpoint/{0}".format(endpoint.uid))
        self.assertEqual(status, 200)

        # Change its UID and framework UID
        endpoint_data = json.loads(response)
        endpoint_data["uid"] = "other-uid"
        endpoint_data["name"] = "other-name"
        endpoint_data["sender"] = "other-framework"

        # Send the 'discovered' event
        status, response = self._http_post("endpoints", json.dumps([endpoint_data]))
        self.assertEqual(status, 200)
        self.assertEqual(response, "OK")

        # Ensure that the service has been registered
        imported_endpoint = importer.endpoints[endpoint_data["uid"]]
        self.assertEqual(imported_endpoint.uid, endpoint_data["uid"])
        self.assertEqual(imported_endpoint.framework, endpoint_data["sender"])
        self.assertEqual(imported_endpoint.name, endpoint_data["name"])

    def testDiscovered(self) -> None:
        """
        Tests the send_discovered' method
        """
        # Register an exporter
        context = self.framework.get_bundle_context()
        exporter = Exporter(context)
        context.register_service(pelix.remote.SERVICE_EXPORT_PROVIDER, exporter, {})

        # Register a service
        context.register_service("sample.spec", object(), {pelix.remote.PROP_EXPORTED_INTERFACES: "*"})

        # Get the endpoint bean
        endpoint = exporter.endpoints[-1]

        # Start a new HTTP server
        with use_ipopo(context) as ipopo:
            # Instantiate remote service components
            # ... HTTP server
            http = ipopo.instantiate(
                "pelix.http.service.basic.factory", "http-server-2", {"pelix.http.port": 0}
            )

        # Keep the HTTP server port
        port = http.get_access()[1]

        # Replace the dispatcher servlet
        servlet = FakeSerlvet()
        servlet_path = (self.servlet.get_access() or [])[1]
        http.unregister(servlet_path)
        http.register_servlet(servlet_path, servlet)

        for with_trailing in (True, False):
            # Test with a trailing slash in the path
            path = servlet_path
            if with_trailing:
                if path[-1] != "/":
                    path += "/"

            elif path[-1] == "/":
                path = path[:-1]

            # Send the discovered packet
            self.assertTrue(self.servlet.send_discovered("localhost", port, path))

            # Check that the servlet has been correctly called
            assert servlet.data is not None
            content = json.loads(servlet.data)

            # Should've got a single endpoint
            self.assertEqual(len(content), 1)
            for key, attr in (("uid", "uid"), ("sender", "framework"), ("name", "name")):
                self.assertEqual(content[0][key], getattr(endpoint, attr))

        # Test with a servlet error (no error should be raised)
        servlet.error = True
        self.assertFalse(self.servlet.send_discovered("localhost", port, servlet_path))

        # Test with a connection error
        self.assertFalse(self.servlet.send_discovered("localhost", -1, servlet_path))
