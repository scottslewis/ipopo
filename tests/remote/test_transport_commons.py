#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the Remote Services abstract transport classes

:author: Thomas Calmant
"""

import unittest
import uuid
from typing import Any, Dict, List, Optional, cast

import pelix.constants
import pelix.framework
import pelix.remote
import pelix.remote.transport.commons as commons
from pelix.internals.registry import ServiceReference
from pelix.ipopo.constants import use_ipopo
from pelix.ipopo.decorators import ComponentFactory, Property, Provides
from pelix.remote import RemoteServiceDispatcher, RemoteServiceError
from pelix.remote.beans import ImportEndpoint

# ------------------------------------------------------------------------------

__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Test factories
TEST_EXPORTER_FACTORY = "test-endpoint-exporter-factory"
TEST_IMPORTER_FACTORY = "test-endpoint-importer-factory"

# RS configuration
TEST_CONFIGURATION = "test.config"

# Test property
TEST_PROPERTY = "test.config.test_property"

# Events
EXPORT_MAKE = 1
IMPORT_MAKE = 2
IMPORT_CLEAR = 3
SERVICE_CALLED = 4

# ------------------------------------------------------------------------------


class DummyService:
    """
    Dummy exported service
    """

    def __init__(self) -> None:
        """
        Sets up a random value to be returned by the service method
        """
        self.value = uuid.uuid4()
        self.events: List[int] = []

    def clear(self) -> None:
        """
        Clears the state
        """
        del self.events[:]

    def call_me(self) -> Any:
        """
        Sample call
        """
        self.events.append(SERVICE_CALLED)
        return self.value


@ComponentFactory(TEST_EXPORTER_FACTORY)
@Provides(pelix.remote.RemoteServiceExportProvider)
@Property("_kinds", pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED, (TEST_CONFIGURATION,))
class Exporter(commons.AbstractRpcServiceExporter):
    """
    Service exporter
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        # Call parent
        super(Exporter, self).__init__()

        self.events: List[int] = []
        self.raise_exception = False

    def clear(self) -> None:
        """
        Clears the state
        """
        del self.events[:]

    def make_endpoint_properties(
        self, svc_ref: ServiceReference[Any], name: str, fw_uid: str
    ) -> Dict[str, Any]:
        """
        Prepare properties for the ExportEndpoint to be created

        :param svc_ref: Service reference
        :param name: Endpoint name
        :param fw_uid: Framework UID
        :return: A dictionary of extra endpoint properties
        """
        self.events.append(EXPORT_MAKE)
        return {TEST_PROPERTY: fw_uid}


# ------------------------------------------------------------------------------


class Proxy:
    """
    Small test proxy
    """

    def __init__(self, fw_uid: Optional[str]) -> None:
        """
        Sets up proxy data
        """
        self.fw_uid = fw_uid


@ComponentFactory(TEST_IMPORTER_FACTORY)
@Provides(pelix.remote.RemoteServiceImportEndpointListener)
@Property("_kinds", pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED, (TEST_CONFIGURATION,))
class Importer(commons.AbstractRpcServiceImporter):
    """
    Service importer
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        # Call parent
        super(Importer, self).__init__()

        self.events: List[int] = []
        self.raise_exception = False

    def clear(self) -> None:
        """
        Clears the state
        """
        del self.events[:]

    def make_service_proxy(self, endpoint: ImportEndpoint) -> Any:
        """
        Creates the proxy for the given ImportEndpoint

        :param endpoint: An ImportEndpoint bean
        :return: A service proxy
        """
        self.events.append(IMPORT_MAKE)
        fw_uid = endpoint.properties.get(TEST_PROPERTY)
        return Proxy(fw_uid)

    def clear_service_proxy(self, endpoint: ImportEndpoint) -> None:
        """
        Destroys the proxy made for the given ImportEndpoint

        :param endpoint: An ImportEndpoint bean
        """
        self.events.append(IMPORT_CLEAR)


# ------------------------------------------------------------------------------


class AbstractCommonExporterTest(unittest.TestCase):
    """
    Tests for the common code for exporters
    """

    framework: pelix.framework.Framework
    dispatcher: RemoteServiceDispatcher

    def setUp(self) -> None:
        """
        Sets up the test
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(("pelix.ipopo.core", "pelix.remote.dispatcher"))
        self.framework.start()

        # Get the framework UID
        context = self.framework.get_bundle_context()
        self.framework_uid = context.get_property(pelix.constants.FRAMEWORK_UID)

        # Get the dispatcher and the imports registry
        svc_ref = context.get_service_reference(pelix.remote.RemoteServiceDispatcher)
        assert svc_ref is not None
        self.dispatcher = context.get_service(svc_ref)

    def tearDown(self) -> None:
        """
        Cleans up for next test
        """
        # Stop the framework
        self.framework.stop()
        pelix.framework.FrameworkFactory.delete_framework()

        # Clean up members
        self.framework = None  # type: ignore
        self.dispatcher = None  # type: ignore

    def _install_exporter(self) -> Exporter:
        """
        Installs the service exporter

        :return: The Exporter component instance
        """
        context = self.framework.get_bundle_context()
        with use_ipopo(context) as ipopo:
            # Register the factory
            ipopo.register_factory(context, Exporter)

            # Instantiate the component
            return cast(Exporter, ipopo.instantiate(TEST_EXPORTER_FACTORY, "exporter", {}))

    def testExportAny(self) -> None:
        """
        Tests the call to the exporter, even if no configuration is given
        """
        # Install the export transport
        exporter = self._install_exporter()
        self.assertListEqual(exporter.events, [])

        # Register an exported service
        context = self.framework.get_bundle_context()
        service = object()
        svc_reg = context.register_service(
            "sample.spec", service, {pelix.remote.PROP_EXPORTED_INTERFACES: "*"}
        )

        # The exporter must have been called
        self.assertListEqual(exporter.events, [EXPORT_MAKE])
        exporter.clear()

        # Check the dispatcher content
        self.assertEqual(len(self.dispatcher.get_endpoints()), 1, "Export endpoint creation error ?")

        # Update the service
        svc_reg.set_properties({"some.property": 42})

        # Unregister the service
        svc_reg.unregister()

        # No call of the exporter
        self.assertListEqual(exporter.events, [])

    def testExportConfig(self) -> None:
        """
        Tests the call to the exporter, with a given configuration
        """
        # Install the export transport
        exporter = self._install_exporter()
        self.assertListEqual(exporter.events, [])

        for config in (exporter._kinds, "*"):
            # Register an exported service
            context = self.framework.get_bundle_context()
            service = object()
            svc_reg = context.register_service(
                "sample.spec",
                service,
                {pelix.remote.PROP_EXPORTED_INTERFACES: "*", pelix.remote.PROP_EXPORTED_CONFIGS: config},
            )

            # Check if handle works correctly
            self.assertTrue(exporter.handles(config), "Exporter doesn't handle {0}".format(config))

            # The exporter must have been called
            self.assertListEqual(exporter.events, [EXPORT_MAKE])
            exporter.clear()

            # Check the dispatcher content
            self.assertEqual(len(self.dispatcher.get_endpoints()), 1, "Export endpoint creation error ?")

            # Unregister the service
            svc_reg.unregister()

    def testExportDispatch(self) -> None:
        """
        Tests the call to the exported service
        """
        # Install the export transport
        exporter = self._install_exporter()

        # Register an exported service
        context = self.framework.get_bundle_context()
        service = DummyService()
        svc_reg = context.register_service(
            "sample.spec", service, {pelix.remote.PROP_EXPORTED_INTERFACES: "*"}
        )

        # The exporter must have been called
        self.assertListEqual(exporter.events, [EXPORT_MAKE])
        exporter.clear()

        # Get the export endpoint
        endpoint = self.dispatcher.get_endpoints()[0]

        # Call the test method
        method_name = "{0}.{1}".format(endpoint.name, "call_me")
        self.assertEqual(exporter.dispatch(method_name, []), service.value)
        self.assertListEqual(service.events, [SERVICE_CALLED], "Service not called")
        service.clear()

        # Call an unknown method
        self.assertRaises(
            RemoteServiceError, exporter.dispatch, "{0}.{1}".format(endpoint.name, "unknown"), []
        )

        # Unregister the service
        svc_reg.unregister()

        # An exception must be raised
        self.assertRaises(RemoteServiceError, exporter.dispatch, method_name, [])
        self.assertListEqual(service.events, [], "Service called after unregistration")

    def testExportRename(self) -> None:
        """
        Tests the rename of an exported endpoint
        """
        # Install the export transport
        exporter = self._install_exporter()

        # Register an exported service
        context = self.framework.get_bundle_context()
        service = DummyService()
        service_2 = DummyService()
        svc_reg = context.register_service(
            "sample.spec", service, {pelix.remote.PROP_EXPORTED_INTERFACES: "*"}
        )

        # Get the export endpoint
        endpoint = self.dispatcher.get_endpoints()[0]

        # Call the test method
        method_name = "{0}.{1}".format(endpoint.name, "call_me")
        self.assertEqual(exporter.dispatch(method_name, []), service.value)
        service.clear()

        # Update the service endpoint name
        name = "endpoint_test"
        svc_reg.set_properties({pelix.remote.PROP_ENDPOINT_NAME: name})

        # Ensure the modification has been stored
        self.assertEqual(endpoint.name, name)

        # Call the test method
        method_name = "{0}.{1}".format(name, "call_me")
        self.assertEqual(exporter.dispatch(method_name, []), service.value)
        self.assertListEqual(service.events, [SERVICE_CALLED], "Service not called")
        service.clear()

        # Update another property
        svc_reg.set_properties({pelix.remote.PROP_ENDPOINT_NAME: name, "other.prop": 42})

        # Call the test method
        self.assertEqual(exporter.dispatch(method_name, []), service.value)
        self.assertListEqual(service.events, [SERVICE_CALLED], "Service not called")
        service.clear()

        # Register another service with the same name
        svc_reg_2 = context.register_service(
            "sample.spec",
            service_2,
            {pelix.remote.PROP_EXPORTED_INTERFACES: "*", pelix.remote.PROP_ENDPOINT_NAME: name},
        )

        # Call the test method
        # (the replacement endpoint should not be callable yet)
        self.assertEqual(exporter.dispatch(method_name, []), service.value)
        # The second service must be callable now
        self.assertListEqual(service.events, [SERVICE_CALLED], "Old service not called")
        self.assertListEqual(service_2.events, [], "New service called after registration")
        service.clear()
        service_2.clear()

        # Unregister the service
        svc_reg.unregister()

        # Check replacement of an endpoint by a previously
        # refused one.

        # Call the test method (the new replacement endpoint should be used)
        self.assertEqual(exporter.dispatch(method_name, []), service_2.value)

        # The second service must be callable now
        self.assertListEqual(service_2.events, [SERVICE_CALLED], "New service not called")
        self.assertListEqual(service.events, [], "Old service called after unregistration")
        service.clear()
        service_2.clear()

        # Unregister the second service
        svc_reg_2.unregister()


# ------------------------------------------------------------------------------


class AbstractCommonImporterTest(unittest.TestCase):
    """
    Tests for the common importer
    """

    framework: pelix.framework.Framework
    registry: pelix.remote.RemoteServiceRegistry

    def setUp(self) -> None:
        """
        Sets up the test
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(("pelix.ipopo.core", "pelix.remote.registry"))
        self.framework.start()

        # Get the framework UID
        context = self.framework.get_bundle_context()
        self.framework_uid = context.get_property(pelix.constants.FRAMEWORK_UID)

        # Get the imports registry
        svc_ref = context.get_service_reference(pelix.remote.RemoteServiceRegistry)
        assert svc_ref is not None
        self.registry = context.get_service(svc_ref)

    def tearDown(self) -> None:
        """
        Cleans up for next test
        """
        # Stop the framework
        self.framework.stop()
        pelix.framework.FrameworkFactory.delete_framework()

        # Clean up members
        self.framework = None  # type: ignore
        self.registry = None  # type: ignore

    def _install_importer(self) -> Importer:
        """
        Installs the service importer

        :return: The Importer component instance
        """
        context = self.framework.get_bundle_context()
        with use_ipopo(context) as ipopo:
            # Register the factory
            ipopo.register_factory(context, Importer)

            # Instantiate the component
            return cast(Importer, ipopo.instantiate(TEST_IMPORTER_FACTORY, "importer", {}))

    def testImportAny(self) -> None:
        """
        Tests the import of an endpoint for any configuration
        """
        # Install the importer
        importer = self._install_importer()

        # Prepare an import endpoint matching any configuration
        endpoint = ImportEndpoint("import-uid", "other-framework", "*", "endpoint_name", ["some.spec"], {})

        # Ensure the importer has not been called yet
        self.assertListEqual(importer.events, [], "Importer called before registration")

        # Register it
        self.registry.add(endpoint)
        self.assertListEqual(importer.events, [IMPORT_MAKE], "Importer not called after registration")
        importer.clear()

        # Update it
        props = endpoint.properties.copy()
        props["other.value"] = 42
        self.registry.update(endpoint.uid, props)

        # The import has not been called
        self.assertListEqual(importer.events, [], "Importer called after update")

        # Clear it
        self.registry.remove(endpoint.uid)
        self.assertListEqual(importer.events, [IMPORT_CLEAR], "Importer not called after unregistration")

    def testImportUnknownConfig(self) -> None:
        """
        Tests the import of an endpoint for an unknown configuration
        """
        # Install the importer
        importer = self._install_importer()

        # Prepare an import endpoint with an unknown configuration
        endpoint = ImportEndpoint(
            "import-uid", "other-framework", "unknown-config", "endpoint_name", ["some.spec"], {}
        )

        # Register it
        self.registry.add(endpoint)
        self.assertListEqual(importer.events, [], "Importer called for an unknown configuration")

        # Remove it
        self.registry.remove(endpoint.uid)
        self.assertListEqual(importer.events, [], "Importer called for an unknown configuration")

    def testImportKnownConfig(self) -> None:
        """
        Tests the import of an endpoint for a known configuration
        """
        # Install the importer
        importer = self._install_importer()

        # Prepare an import endpoint with a known configuration
        endpoint = ImportEndpoint(
            "import-uid", "other-framework", importer._kinds, "endpoint_name", ["some.spec"], {}
        )

        # Register it
        self.registry.add(endpoint)
        self.assertListEqual(importer.events, [IMPORT_MAKE], "Importer not called for a known configuration")
        importer.clear()

        # Clear it
        self.registry.remove(endpoint.uid)
        self.assertListEqual(importer.events, [IMPORT_CLEAR], "Importer not called after unregistration")

    def testLostFramework(self) -> None:
        """
        Tests the loss of a framework
        """
        # Install the importer
        importer = self._install_importer()

        # Prepare an import endpoint matching any configuration
        fw_uid = "other-framework"
        endpoint = ImportEndpoint("import-uid", fw_uid, "*", "endpoint_name", ["some.spec"], {})

        # Register it
        self.registry.add(endpoint)
        self.assertListEqual(importer.events, [IMPORT_MAKE], "Importer not called after registration")
        importer.clear()

        # Clear it
        self.registry.lost_framework(endpoint.framework)
        self.assertListEqual(importer.events, [IMPORT_CLEAR], "Importer not called after framework loss")


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
