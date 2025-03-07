#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the Remote Services Imports Registry

:author: Thomas Calmant
"""

import unittest
from typing import Any, Dict, List

import pelix.constants
import pelix.framework
import pelix.remote
import pelix.remote.beans as beans

# ------------------------------------------------------------------------------

__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

ADDED = 1
UPDATED = 2
REMOVED = 3

# ------------------------------------------------------------------------------


class ImportListener:
    """
    Imports listener
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        self.events: List[int] = []
        self.raise_exception = False

    def clear(self) -> None:
        """
        Clears the listener state
        """
        del self.events[:]

    def endpoint_added(self, endpoint: beans.ImportEndpoint) -> None:
        """
        Endpoint registered
        """
        self.events.append(ADDED)
        if self.raise_exception:
            raise Exception("Addition exception")

    def endpoint_updated(self, endpoint: beans.ImportEndpoint, properties: Dict[str, Any]) -> None:
        """
        Endpoint updated
        """
        self.events.append(UPDATED)
        if self.raise_exception:
            raise Exception("Update exception")

    def endpoint_removed(self, uid: str) -> None:
        """
        Endpoint removed
        """
        self.events.append(REMOVED)
        if self.raise_exception:
            raise Exception("Removal exception")


# ------------------------------------------------------------------------------


class ImportsRegistryTest(unittest.TestCase):
    """
    Tests for the Remote Services imports registry
    """

    framework: pelix.framework.Framework
    service: pelix.remote.RemoteServiceRegistry

    def setUp(self) -> None:
        """
        Sets up the test
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(["pelix.ipopo.core"])
        self.framework.start()

        # Install the registry
        context = self.framework.get_bundle_context()
        context.install_bundle("pelix.remote.registry").start()

        # Get the framework UID
        self.framework_uid = context.get_property(pelix.constants.FRAMEWORK_UID)

        # Get the service
        svc_ref = context.get_service_reference(pelix.remote.RemoteServiceRegistry)
        assert svc_ref is not None
        self.service = context.get_service(svc_ref)

    def tearDown(self) -> None:
        """
        Cleans up for next test
        """
        # Stop the framework
        pelix.framework.FrameworkFactory.delete_framework()

        self.framework = None  # type: ignore
        self.service = None  # type: ignore

    def testAdd(self) -> None:
        """
        Tests the addition of an endpoint
        """
        # Prepare an ImportEndpoint
        endpoint = beans.ImportEndpoint(
            "service-uid", "some-framework", ["configA", "configB"], "name", "test.spec", {}
        )

        endpoint_same = beans.ImportEndpoint(
            "service-uid", "some-other-framework", ["configA", "configB"], "other-name", "other.spec", {}
        )

        endpoint_local = beans.ImportEndpoint(
            "other-service-uid", self.framework_uid, ["configA", "configB"], "name", "test.spec", {}
        )

        # Register the endpoint
        self.assertTrue(self.service.add(endpoint), "ImportEndpoint refused")

        # Refuse next registration (same bean)
        self.assertFalse(self.service.add(endpoint), "ImportEndpoint double-registration")

        # Refuse endpoints with the same UID
        self.assertFalse(self.service.add(endpoint_same), "ImportEndpoint double-UID")

        # Refuse endpoints the same framework UID
        self.assertFalse(self.service.add(endpoint_local), "ImportEndpoint local framework")

    def testUpdate(self) -> None:
        """
        Tests the update of an endpoint
        """
        # Prepare an ImportEndpoint
        endpoint = beans.ImportEndpoint(
            "service-uid", "some-framework", ["configA", "configB"], "name", "test.spec", {}
        )

        # No error on unknown endpoint
        self.assertFalse(
            self.service.update(endpoint.uid, {}), "Update of an unknown endpoint has been accepted"
        )

        # Register the endpoint
        self.assertTrue(self.service.add(endpoint), "Addition refused")

        # Update must succeed
        self.assertTrue(self.service.update(endpoint.uid, {}), "Error updating an endpoint")

    def testRemove(self) -> None:
        """
        Tests the removal of an endpoint
        """
        # Prepare an ImportEndpoint
        endpoint = beans.ImportEndpoint(
            "service-uid", "some-framework", ["configA", "configB"], "name", "test.spec", {}
        )

        # No error on unknown endpoint
        self.assertFalse(
            self.service.remove(endpoint.uid), "Removal of an unknown endpoint has been accepted"
        )

        # Register the endpoint
        self.assertTrue(self.service.add(endpoint), "Addition refused")

        # Removal must succeed
        self.assertTrue(self.service.remove(endpoint.uid), "Error removing an endpoint")

    def testLost(self) -> None:
        """
        Tests the lost framework event
        """
        endpoint = beans.ImportEndpoint(
            "service-uid", "some-framework", ["configA", "configB"], "name", "test.spec", {}
        )

        # No error if the framework wasn't known
        self.service.lost_framework("other-framework")

        # Register the endpoint
        self.assertTrue(self.service.add(endpoint), "ImportEndpoint refused")

        # Loss must succeed
        self.service.lost_framework(endpoint.framework)

        # The endpoint must have been removed
        self.assertFalse(self.service.remove(endpoint.uid), "Removal of a lost endpoint has been accepted")
        self.assertFalse(self.service.update(endpoint.uid, {}), "Update of a lost endpoint has been accepted")
        self.assertTrue(self.service.add(endpoint), "Addition refused")

    def testListener(self) -> None:
        """
        Tests the listener
        """
        # Prepare endpoints
        context = self.framework.get_bundle_context()
        endpoint = beans.ImportEndpoint(
            "service-uid", "some-framework", ["configA", "configB"], "name", "test.spec", {}
        )

        for raise_exception in (False, True):
            # Prepare a listener
            listener = ImportListener()
            listener.raise_exception = raise_exception

            # Register a endpoint
            self.assertTrue(self.service.add(endpoint), "ImportEndpoint refused")

            # Register the listener
            svc_reg = context.register_service(
                pelix.remote.SERVICE_IMPORT_ENDPOINT_LISTENER,
                listener,
                {pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED: "configA"},
            )

            # The listener must have been notified
            self.assertListEqual(listener.events, [ADDED], "Listener not notified of addition")
            listener.clear()

            # Update the endpoint
            self.service.update(endpoint.uid, {})
            self.assertListEqual(listener.events, [UPDATED], "Listener not notified of update")
            listener.clear()

            # Remove it
            self.service.remove(endpoint.uid)
            self.assertListEqual(listener.events, [REMOVED], "Listener not notified of removal")
            listener.clear()

            # Re-register the endpoint and lose the framework
            self.assertTrue(self.service.add(endpoint), "ImportEndpoint refused")
            self.service.lost_framework(endpoint.framework)

            self.assertListEqual(
                listener.events, [ADDED, REMOVED], "Bad notification of the loss of a framework"
            )

            # Unregister the service
            svc_reg.unregister()

    def testSynonyms(self) -> None:
        """
        Tests synonyms property handling
        """
        # Specifications
        spec_1 = "sample.spec"
        spec_2 = "sample.spec2"
        spec_3 = "sample.spec3"
        python_specs = ["python:/{0}".format(spec) for spec in (spec_2, spec_3)]
        spec_java = "org.pelix.sample.ISpec2"
        java_specs = ["java:/{0}".format(spec_java)]

        # Prepare an ImportEndpoint
        endpoint = beans.ImportEndpoint(
            "service-uid",
            "some-framework",
            ["configA", "configB"],
            "name",
            # "Normal" specification
            spec_1,
            #  Synonyms
            {pelix.remote.PROP_SYNONYMS: python_specs + java_specs},
        )

        # Register the endpoint
        self.service.add(endpoint)

        # Check its specifications: Python ones don't have a prefix
        self.assertIn(spec_1, endpoint.specifications)
        self.assertIn(spec_2, endpoint.specifications)
        self.assertIn(spec_3, endpoint.specifications)

        # Java one is kept as is
        self.assertIn(java_specs[0], endpoint.specifications)


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
