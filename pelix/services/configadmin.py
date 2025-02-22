#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
ConfigurationAdmin implementation

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

TODO: Stabilize implementation of managed service factories
FIXME: Add tests for the configuration of managed service factories
"""

import json
import logging
import os
import threading
import uuid
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Protocol, Set, Tuple, Union, cast

import pelix.constants
import pelix.ldapfilter as ldapfilter
import pelix.services as services
import pelix.threadpool
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Instantiate,
    Invalidate,
    Property,
    Provides,
    Requires,
    UnbindField,
    Validate,
)

if TYPE_CHECKING:
    from pelix.framework import BundleContext
    from pelix.internals.registry import ServiceReference

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

SERVICE_CONFIGADMIN_DIRECTORY = "pelix.services.configadmin.directory"
""" Configurations directory service specification """

SERVICE_CONFIGURATION_ADMIN_PRIVATE = "pelix.services.configadmin.private"
"""
Private version of ConfigAdmin, to handle loop-requirements ("that will do")
"""


@pelix.constants.Specification(SERVICE_CONFIGADMIN_DIRECTORY)
class IConfigurationAdminDirectory(Protocol):
    """
    Specification of a configuration admin directory service
    """

    def list_configurations(
        self, ldap_filter: Union[None, str, ldapfilter.LdapFilterOrCriteria] = None
    ) -> Iterable[services.Configuration]:
        """
        Lists known configuration
        """
        ...

    def get_configuration(self, pid: str) -> services.Configuration:
        """
        Returns an existing configuration
        """
        ...

    def get_factory_configurations(self, factory_pid: str) -> Optional[Iterable[services.Configuration]]:
        """
        List available configurations for the given factory
        """
        ...

    def add(
        self,
        pid: str,
        properties: Optional[Dict[str, Any]],
        persistence: services.IConfigurationAdminPersistence,
        factory_pid: Optional[str] = None,
    ) -> services.Configuration:
        """
        Add a configuration to the directory
        """
        ...

    def update(self, pid: str, properties: Dict[str, Any]) -> None:
        """
        Update a configuration
        """
        ...

    def delete(self, pid: str) -> None:
        """
        Deletes the given configuration
        """
        ...


# ------------------------------------------------------------------------------


class Configuration(services.Configuration):
    """
    Configuration object
    """

    def __init__(
        self,
        pid: str,
        properties: Optional[Dict[str, Any]],
        config_admin: services.IConfigurationAdmin,
        persistence: services.IConfigurationAdminPersistence,
        factory_pid: Optional[str] = None,
    ) -> None:
        """
        :param pid: The configuration PID
        :param properties: The initial properties of the configuration
        :param config_admin: The parent ConfigurationAdmin service
        :param persistence: The configuration persistence handler
        :param factory_pid: An optional factory PID
        """
        # Configuration PID
        self.__pid = pid

        # Factory PID
        self.__factory_pid = factory_pid

        # Properties
        self.__properties: Optional[Dict[str, Any]] = None
        self.__lock = threading.RLock()

        # Associated services
        self.__config_admin = config_admin
        self.__persistence = persistence

        # Configuration state
        self.__updated: bool = False
        self.__deleted: bool = False
        self.__location: Optional[str] = None

        # Update using given properties, if any
        self.__properties_update(properties)

    def __str__(self) -> str:
        """
        String representation
        """
        if self.__factory_pid:
            kind = f"FactoryConfiguration({self.__factory_pid}, "
        else:
            kind = "Configuration("

        return f"{kind}pid={self.__pid}, updated={self.__updated}, deleted={self.__deleted})"

    def get_bundle_location(self) -> Optional[str]:
        """
        Get the bundle location.
        Returns the bundle location to which this configuration is bound,
        or None if it is not yet bound to a bundle location.

        :return: The location associated to the configuration
        """
        return self.__location

    def set_bundle_location(self, location: Optional[str]) -> None:
        """
        Bind this Configuration object to the specified bundle location.
        If the location parameter is None then the Configuration object
        will not be bound to a location.
        It will be set to the bundle's location before the first time a
        Managed Service/Managed Service Factory receives this Configuration
        object via the updated method and before any plugins are called.
        The bundle location will be set persistently.

        :param location: A bundle location
        """
        self.__location = location

    def get_factory_pid(self) -> Optional[str]:
        """
        For a factory configuration returns the PID of the corresponding
        Managed Service Factory, else returns None.

        :return: The factory PID or None
        """
        return self.__factory_pid

    def get_pid(self) -> str:
        """
        Returns the PID of this configuration

        :return: The configuration PID
        """
        return self.__pid

    def get_properties(self) -> Optional[Dict[str, Any]]:
        """
        Return the properties of this Configuration object.
        The Dictionary object returned is a private copy for the caller and may
        be changed without influencing the stored configuration.

        If called just after the configuration is created and before update has
        been called, this method returns None.

        :return: A private copy of the properties for the caller or null.
                 These properties must not contain the "service.bundleLocation"
                 property. The value of this property may be obtained from the
                 get_bundle_location() method.
        """
        with self.__lock:
            if self.__deleted:
                raise ValueError(f"{self.__pid} has been deleted")
            elif not self.__updated:
                # Fresh configuration
                return None

            if self.__properties is None:
                # No properties set
                return None

            # Filter a copy of the properties
            props = self.__properties.copy()

            try:
                del props[services.CONFIG_PROP_BUNDLE_LOCATION]
            except KeyError:
                # Ignore
                pass

            return props

    def is_valid(self) -> bool:
        """
        Checks if this configuration has been updated at least once and has not
        been deleted.

        :return: True if the configuration has properties and has not been deleted
        """
        return self.__updated and not self.__deleted

    def __properties_update(self, properties: Optional[Dict[str, Any]]) -> bool:
        """
        Internal update of configuration properties. Does not notifies the
        ConfigurationAdmin of this modification.

        :param properties: the new set of properties for this configuration
        :return: True if the properties have been updated, else False
        """
        if not properties:
            # Nothing to do
            return False

        with self.__lock:
            # Make a copy of the properties
            properties = properties.copy()

            # Override properties
            properties[services.CONFIG_PROP_PID] = self.__pid

            if self.__location:
                properties[services.CONFIG_PROP_BUNDLE_LOCATION] = self.__location

            if self.__factory_pid:
                properties[services.CONFIG_PROP_FACTORY_PID] = self.__factory_pid

            # See if new properties are different
            if properties == self.__properties:
                return False

            # Store the copy (before storing data)
            self.__properties = properties
            self.__updated = True

            # Store the data
            # it will cause FileInstall to update this configuration again, but
            # this will ignored because self.__properties has already been
            # saved
            if self.__persistence is not None:
                self.__persistence.store(self.__pid, properties)
            return True

    def reload(self) -> None:
        """
        Reloads the configuration file using the persistence service

        :raise IOError: File not found/readable
        :raise ValueError: Invalid file content
        """
        if self.__persistence is not None:
            self.update(self.__persistence.load(self.__pid))

    def update(self, properties: Optional[Dict[str, Any]] = None) -> None:
        """
        If called without properties, only notifies listeners

        Update the properties of this Configuration object.
        Stores the properties in persistent storage after adding or overwriting
        the following properties:

        * "service.pid" : is set to be the PID of this configuration.
        * "service.factoryPid" : if this is a factory configuration it is set
          to the factory PID else it is not set.

        These system properties are all of type String.

        If the corresponding Managed Service/Managed Service Factory is
        registered, its updated method must be called asynchronously.
        Else, this callback is delayed until aforementioned registration
        occurs.

        Also initiates an asynchronous call to all ConfigurationListeners with
        a ConfigurationEvent.CM_UPDATED event.

        :param properties: the new set of properties for this configuration
        :raise IOError: Error storing the configuration
        """
        with self.__lock:
            # Update properties
            if self.__properties_update(properties):
                # Update configurations, if something changed
                cast(ConfigurationAdmin, self.__config_admin)._update(self)

    def delete(self, directory_updated: bool = False) -> None:
        """
        Delete this configuration

        :param directory_updated: If True, tell ConfigurationAdmin to not
        recall the directory of this deletion (internal use only)
        """
        with self.__lock:
            if self.__deleted:
                # Nothing to do
                return

            # Update status
            self.__deleted = True

            # Notify ConfigurationAdmin, notify services only if the
            # configuration had been updated before
            cast(ConfigurationAdmin, self.__config_admin)._delete(self, self.__updated, directory_updated)

            # Remove the file
            self.__persistence.delete(self.__pid)

            # Clean up
            if self.__properties:
                self.__properties.clear()

            self.__pid = ""

    def matches(self, ldap_filter: Optional[ldapfilter.LdapFilterOrCriteria]) -> bool:
        """
        Tests if this configuration matches the given filter.

        :param ldap_filter: A parsed LDAP filter object
        :return: True if the properties of this configuration matches the filter
        """
        if not self.is_valid():
            # Do not test invalid configurations
            return False

        return ldap_filter is None or ldap_filter.matches(self.__properties or {})


# ------------------------------------------------------------------------------


@ComponentFactory()
@Provides(IConfigurationAdminDirectory)
@Requires("_admin", SERVICE_CONFIGURATION_ADMIN_PRIVATE)
@Instantiate("pelix-services-configuration-directory")
class ConfigurationDirectory(IConfigurationAdminDirectory):
    """
    A configuration directory
    """

    _admin: services.IConfigurationAdmin

    def __init__(self) -> None:
        """
        Sets up members
        """
        # PID -> services.Configuration
        self.__configurations: Dict[str, Configuration] = {}

        # Factory PIDs -> set(Configuration)
        self.__factories: Dict[str, Set[Configuration]] = {}

        # Lock
        self.__lock = threading.Lock()

    def exists(self, pid: str) -> bool:
        """
        Checks if the given PID exists in the directory

        :param pid: A configuration PID
        :return: True if the PID already exists
        """
        return pid in self.__configurations or pid in self.__factories

    def get_configuration(self, pid: str) -> services.Configuration:
        """
        Retrieves the configuration with the given PID

        :param pid: PID of the configuration
        :return: The configuration with the given PID
        :raise KeyError: Unknown PID
        """
        return self.__configurations[pid]

    def get_factory_configurations(self, factory_pid: str) -> Set[Configuration]:
        """
        Retrieves the configurations with the given factory PID

        :param factory_pid: A factory PID
        :return: The set of matching configuration
        """
        return set(self.__factories.get(factory_pid, []))

    def list_configurations(
        self, ldap_filter: Union[None, str, ldapfilter.LdapFilterOrCriteria] = None
    ) -> Iterable[services.Configuration]:
        """
        Returns the list of stored configurations

        :param ldap_filter: Optional LDAP filter
        :return: The set of matching configurations
        :raise ValueError: Invalid LDAP filter
        """
        if not ldap_filter:
            return set(self.__configurations.values())

        # Using an LDAP filter
        ldap_filter = ldapfilter.get_ldap_filter(ldap_filter)
        return {config for config in self.__configurations.values() if config.matches(ldap_filter)}

    def add(
        self,
        pid: str,
        properties: Optional[Dict[str, Any]],
        loader: services.IConfigurationAdminPersistence,
        factory_pid: Optional[str] = None,
    ) -> services.Configuration:
        """
        Creates a new configuration bean

        :param pid: PID of the configuration
        :param properties: Initial properties (can be None)
        :param loader: Persistence service associated to the configuration
        :param factory_pid: Set if the configuration is a factory (not used)
        :return: The new configuration bean
        :raise KeyError: PID already used
        :raise ValueError: Invalid PID or loader
        """
        with self.__lock:
            if pid in self.__configurations:
                raise KeyError("Already known configuration: {pid}")
            elif not pid:
                raise ValueError("Configuration with an empty PID")
            elif pid in self.__factories:
                raise KeyError("PID already used as a factory PID: {pid}")
            elif loader is None:
                raise ValueError("No persistence service associated to {pid}")

            # Make the configuration bean
            configuration = Configuration(pid, properties, self._admin, loader, factory_pid)

            # Store the factory according to the PID
            self.__configurations[pid] = configuration

            # Store the factory PID too
            if factory_pid is not None:
                self.__factories.setdefault(factory_pid, set()).add(configuration)

            return configuration

    def update(self, pid: str, properties: Optional[Dict[str, Any]]) -> None:
        """
        Updates the properties of an existing configuration

        :param pid: PID of a configuration
        :param properties: New properties (replace old dictionary)
        :raise KeyError: Unknown configuration
        :raise IOError: Error writing down the configuration
        """
        with self.__lock:
            # Update properties directly
            self.__configurations[pid].update(properties)

    def delete(self, pid: str) -> None:
        """
        Deletes the configuration with the given PID

        :param pid: PID of a configuration
        :raise KeyError: Unknown configuration
        :raise IOError: Error deleting the configuration file
        """
        with self.__lock:
            # Remove from the configuration dictionary
            config = self.__configurations.pop(pid)

            # Remove from the factory PIDs set
            factory_pid = config.get_factory_pid()
            if factory_pid:
                try:
                    factory_configs = self.__factories[factory_pid]
                    factory_configs.remove(config)
                    if not factory_configs:
                        del self.__factories[factory_pid]
                except KeyError:
                    # Wasn't a known factory configuration
                    _logger.warning("Trying to delete configuration from unknown factory %s", factory_pid)

            # Delete the configuration object
            config.delete(True)


# ------------------------------------------------------------------------------


@ComponentFactory()
@Provides(services.IConfigurationAdmin, controller="_controller")
@Provides(SERVICE_CONFIGURATION_ADMIN_PRIVATE)
@Requires("_directory", IConfigurationAdminDirectory, optional=True)
@Requires(
    "_persistences",
    services.IConfigurationAdminPersistence,
    aggregate=True,
    optional=True,
)
@Requires(
    "_managed",
    services.IManagedService,
    aggregate=True,
    optional=True,
)
@Requires(
    "_managed_factories",
    services.IManagedServiceFactory,
    aggregate=True,
    optional=True,
)
@Instantiate("pelix-services-configuration-admin")
class ConfigurationAdmin(services.IConfigurationAdmin):
    """
    ConfigurationAdmin basic implementation
    """

    # Configurations directory
    _directory: IConfigurationAdminDirectory

    # Persistence providers
    _persistences: List[services.IConfigurationAdminPersistence]

    # Managed services
    _managed: List[services.IManagedService]

    # Managed services factories
    _managed_factories: List[services.IManagedServiceFactory]

    def __init__(self) -> None:
        # Service controller
        self._controller = False

        # Service reference -> Managed Service
        self._managed_refs: Dict["ServiceReference[services.IManagedService]", services.IManagedService] = {}
        self._factories_refs: Dict[
            "ServiceReference[services.IManagedServiceFactory]", services.IManagedServiceFactory
        ] = {}

        # Some safety
        self.__lock = threading.RLock()

        # Update thread pool
        self._pool: Optional[pelix.threadpool.ThreadPool] = None

        # Validation flag
        self.__validated: bool = False

    def __set_up(self) -> None:
        """
        Set up the configuration administration service.
        To be called only when the component has been validated and the service
        controller is set to True.
        """
        # Get existing PIDs
        pids: Set[str] = set()
        for persistence in self._persistences:
            pids.update(persistence.get_pids())

        # Notify services
        self.__notify_pids(pids)

    @Validate
    def _validate(self, _: "BundleContext") -> None:
        """
        Component validated
        """
        with self.__lock:
            # Create the update thread pool
            self._pool = pelix.threadpool.ThreadPool(2, logname="ConfigAdmin")
            self._pool.start()

            # Validation flag
            self.__validated = True

            # If the controller is on, set up the main service
            if self._controller:
                self.__set_up()

    @Invalidate
    def _invalidate(self, _: "BundleContext") -> None:
        """
        Component invalidated
        """
        with self.__lock:
            # Validation flag
            self.__validated = False

            # Stop the pool
            if self._pool is not None:
                self._pool.stop()
                self._pool = None

    @BindField("_directory")
    def _bind_directory(
        self,
        field: str,
        svc: IConfigurationAdminDirectory,
        svc_ref: "ServiceReference[IConfigurationAdminDirectory]",
    ) -> None:
        """
        The configurations directory has been bound
        """
        # Provide the ConfigurationAdmin service, if a controller is there
        self._controller = bool(self._persistences)
        if self.__validated and self._controller:
            # Set up the service
            self.__set_up()

    @BindField("_persistences")
    def _bind_persistence(
        self,
        field: str,
        svc: services.IConfigurationAdminPersistence,
        svc_ref: "ServiceReference[services.IConfigurationAdminPersistence]",
    ) -> None:
        """
        A persistence came in
        """
        self._controller = self._directory is not None
        if self.__validated and self._controller:
            # Set up the service
            self.__set_up()

    @UnbindField("_persistences")
    @UnbindField("_directory")
    def _unbind_directory(self, field: str, svc: Any, svc_ref: "ServiceReference[Any]") -> None:
        """
        The configurations directory has gone
        """
        # Remove the ConfigurationAdmin service
        self._controller = False

    @BindField("_managed")
    def _bind_managed(
        self, field: str, svc: services.IManagedService, svc_ref: "ServiceReference[services.IManagedService]"
    ) -> None:
        """
        A managed service has been bound
        """
        with self.__lock:
            # Store the service reference
            self._managed_refs[svc_ref] = svc

            if self.__validated and self._controller:
                # Update with the associated configuration, if active
                pid = svc_ref.get_property(pelix.constants.SERVICE_PID)
                try:
                    self.__notify_single(pid, svc)
                except KeyError as ex:
                    _logger.error("Error configuring a service: %s", ex)

    @UnbindField("_managed")
    def _unbind_managed(
        self, field: str, svc: services.IManagedService, svc_ref: "ServiceReference[services.IManagedService]"
    ) -> None:
        """
        A managed service has gone
        """
        with self.__lock:
            # Forget the reference
            del self._managed_refs[svc_ref]

    @BindField("_managed_factories")
    def _bind_managed_factory(
        self,
        field: str,
        svc: services.IManagedServiceFactory,
        svc_ref: "ServiceReference[services.IManagedServiceFactory]",
    ) -> None:
        """
        A managed service factory has been bound
        """
        with self.__lock:
            # Store the reference
            self._factories_refs[svc_ref] = svc

            if self.__validated and self._controller:
                # Update with associated configurations
                factory_pid = svc_ref.get_property(pelix.constants.SERVICE_PID)
                self.__notify_factory(factory_pid, svc)

    @UnbindField("_managed_factories")
    def _unbind_managed_factories(
        self,
        field: str,
        svc: services.IManagedServiceFactory,
        svc_ref: "ServiceReference[services.IManagedServiceFactory]",
    ) -> None:
        """
        A managed service has gone
        """
        with self.__lock:
            # Forget the reference
            del self._factories_refs[svc_ref]

    def __notify_pids(self, pids: Iterable[str]) -> None:
        """
        Updates the managed services for the given PIDs.

        This method should be called inside a locked block.

        :param pids: List of PIDs of configurations to load & update
        """
        for pid in pids:
            try:
                # Load the configuration
                config = self.get_configuration(pid)
                if config.is_valid():
                    # Notify corresponding service
                    self._update(config)
            except (IOError, ValueError) as ex:
                _logger.error("Error loading configuration %s: %s", pid, ex)

    def __get_matching_factories(self, factory_pid: str) -> List[services.IManagedServiceFactory]:
        """
        Returns the list of managed service factories that matches the given
        factory PID

        :param factory_pid: A managed service factory PID
        :return: The list of matching factories
        """
        return [
            svc
            for svc_ref, svc in self._factories_refs.items()
            if svc_ref.get_property(pelix.constants.SERVICE_PID) == factory_pid
        ]

    def __get_matching_services(self, pid: str) -> List[services.IManagedService]:
        """
        Returns the list of managed services that matches the given PID

        :param pid: A configuration PID
        :return: The list of services matching the PID
        """
        # Make the list of managed services
        return [
            svc
            for svc_ref, svc in self._managed_refs.items()
            if svc_ref.get_property(pelix.constants.SERVICE_PID) == pid
        ]

    def __notify_single(self, pid: str, svc: services.IManagedService) -> None:
        """
        Adds a call to the updated() method of the given managed service in the
        pool, if a valid configuration has been found for it.

        :param pid: Service Persistent ID
        :param svc: Managed service
        """
        configuration = self.get_configuration(pid)
        if configuration.is_valid():
            # Valid configuration found, update the service
            assert self._pool is not None
            self._pool.enqueue(svc.updated, configuration.get_properties())

    def __notify_factory(self, factory_pid: str, svc: services.IManagedServiceFactory) -> None:
        """
        Adds a call to the updated() method of the given managed service
        factory in the pool, if valid configurations have been found for it.

        :param factory_pid: Factory Persistent ID
        :param svc: Managed service factory
        """
        configurations = self._directory.get_factory_configurations(factory_pid)
        if configurations:
            for configuration in configurations:
                if configuration.is_valid():
                    # Valid configurations found, call update for each one
                    assert self._pool is not None
                    self._pool.enqueue(
                        svc.updated,
                        configuration.get_pid(),
                        configuration.get_properties(),
                    )

    @staticmethod
    def __notify_factories(
        factories: Iterable[services.IManagedServiceFactory], pid: str, properties: Optional[Dict[str, Any]]
    ) -> None:
        """
        Calls the updated(pid, properties) method of managed service factories.

        :param factories: A list of managed service factories
        :param pid: PID of the deleted configuration
        :param properties: New configuration properties
        """
        for svc in factories:
            try:
                # Only give the properties to the service
                svc.updated(pid, properties)
            except Exception as ex:
                _logger.exception("Error updating factory: %s", ex)

    @staticmethod
    def __notify_factories_delete(factories: Iterable[services.IManagedServiceFactory], pid: str) -> None:
        """
        Calls the deleted(pid) method of the given managed service factories.

        :param factories: A list of managed service factories
        :param pid: PID of the deleted configuration
        """
        for svc in factories:
            try:
                svc.deleted(pid)
            except Exception as ex:
                _logger.exception("Error notifying a factory: %s", ex)

    @staticmethod
    def __notify_services(
        managed_services: Iterable[services.IManagedService], properties: Optional[Dict[str, Any]]
    ) -> None:
        """
        Calls the updated(properties) method of managed services.
        Logs errors if necessary.

        :param managed_services: Managed services to be notified
        :param properties: New configuration properties
        """
        for svc in managed_services:
            try:
                # Only give the properties to the service
                svc.updated(properties)
            except Exception as ex:
                _logger.exception("Error updating service: %s", ex)

    def _update(self, configuration: services.Configuration) -> None:
        """
        A configuration has been updated.

        Returns once managed services have been notified.

        :param configuration: The updated configuration
        """
        with self.__lock:
            future = None
            assert self._pool is not None

            # Get configuration data
            factory_pid = configuration.get_factory_pid()
            pid = configuration.get_pid()
            properties = configuration.get_properties()

            if factory_pid:
                # Get the associated factories
                factories = self.__get_matching_factories(factory_pid)
                if factories:
                    # Call them from the pool
                    future = self._pool.enqueue(self.__notify_factories, factories, pid, properties)
            else:
                # Called corresponding managed services
                managed = self.__get_matching_services(configuration.get_pid())
                if managed:
                    # Call them from the pool
                    future = self._pool.enqueue(self.__notify_services, managed, properties)

        if future is not None:
            # Wait for the end of the notification, outside the lock
            future.result()

    def _delete(self, configuration: Configuration, notify_services: bool, directory_updated: bool) -> None:
        """
        A configuration is about to be deleted.

        Returns once managed services have been notified.

        :param configuration: The deleted configuration
        :param notify_services: If True, notify services of the deletion
        :param directory_updated: If True, do not update the directory
        """
        with self.__lock:
            future = None
            assert self._pool is not None

            factory_pid = configuration.get_factory_pid()
            pid = configuration.get_pid()

            # Remove the configuration from the directory
            if not directory_updated:
                self._directory.delete(pid)

            if notify_services:
                if factory_pid:
                    # Get the associated factories
                    factories = self.__get_matching_factories(factory_pid)
                    if factories:
                        # Call them from the pool
                        future = self._pool.enqueue(self.__notify_factories_delete, factories, pid)
                else:
                    # Called corresponding managed services
                    managed = self.__get_matching_services(pid)
                    if managed:
                        # Call them from the pool
                        future = self._pool.enqueue(self.__notify_services, managed, None)

        if future is not None:
            # Wait for the end of the notification, outside the lock
            future.result()

    def create_factory_configuration(self, factory_pid: str) -> services.Configuration:
        """
        Create a new factory Configuration object with a new PID.
        The properties of the new Configuration object are null until the
        first time that its update() method is called.

        :param factory_pid: PID of the factory
        :raise ValueError: Invalid PID
        """
        with self.__lock:
            if factory_pid is None:
                raise ValueError("No factory PID given")

            try:
                # Remove leading-trailing spaces
                factory_pid = factory_pid.strip()
                if not factory_pid:
                    raise ValueError("Empty factory PID")
            except AttributeError:
                # .strip() doesn't exist
                raise ValueError(f"Invalid type of PID: {type(factory_pid).__name__}")

            # Generate a configuration PID
            pid = f"{factory_pid}-{uuid.uuid4()}"

            # Create the new factory configuration
            return self._directory.add(pid, None, self._persistences[0], factory_pid)

    def get_configuration(self, pid: str) -> services.Configuration:
        """
        Get an existing Configuration object from the persistent store, or
        create a new Configuration object.

        :param pid: PID of the factory
        :raise IOError: File not found/readable
        """
        with self.__lock:
            try:
                return self._directory.get_configuration(pid)
            except KeyError:
                # Unknown configuration, look for it
                # (outside the exception block)
                pass

            for persistence in self._persistences[:]:
                if persistence.exists(pid):
                    # Load first existing one
                    properties = persistence.load(pid)
                    break
            else:
                # New configuration, with the best ranked persistence
                properties = {}
                persistence = self._persistences[0]

            # Take care of stored factory PID
            factory_pid = properties.get(services.CONFIG_PROP_FACTORY_PID)

            return self._directory.add(pid, properties, persistence, factory_pid)

    def list_configurations(
        self, ldap_filter: Union[None, str, ldapfilter.LdapFilterOrCriteria] = None
    ) -> Iterable[services.Configuration]:
        """
        List the current Configuration objects which match the filter.

        Only Configuration objects with non-null properties are considered
        current.
        That is, Configuration.get_properties() is guaranteed not to return
        null for each of the returned Configuration objects.

        The syntax of the filter string is as defined in the Filter class.
        The filter can test any configuration properties including the
        following:

        * service.pid (str): the PID under which this is registered
        * service.factoryPid (str): the factory if applicable
        * service.bundleLocation(str): the bundle location

        The filter can also be null, meaning that all Configuration objects
        should be returned.
        """
        with self.__lock:
            return self._directory.list_configurations(ldap_filter)


# ------------------------------------------------------------------------------


@ComponentFactory(services.FACTORY_CONFIGADMIN_JSON)
@Provides(
    [
        services.IConfigurationAdminPersistence,
        services.SERVICE_FILEINSTALL_LISTENERS,
    ]
)
@Requires("_directory", IConfigurationAdminDirectory)
@Property("_conf_folder", "configuration.folder")
@Property("_watched_folder", services.PROP_FILEINSTALL_FOLDER)
class JsonPersistence(services.IConfigurationAdminPersistence):
    """
    JSON configuration persistence
    """

    # Configurations directory
    _directory: IConfigurationAdminDirectory

    def __init__(self) -> None:
        """
        Sets up members
        """
        # Configuration folder
        self._conf_folder: str = ""
        self._watched_folder: str = ""

    def _get_file(self, pid: str) -> str:
        """
        Returns the path to the configuration file for the given PID

        :param pid: A configuration PID
        :return: The name of the configuration file
        """
        return os.path.join(self._conf_folder, f"{pid}.config.js")

    @staticmethod
    def _get_pid(filename: str) -> Optional[str]:
        """
        Extract the PID from the given file name

        :param filename: A file name
        :return: The corresponding PID or None
        """
        # Get the base name
        name = os.path.basename(filename)

        # Remove the extension
        try:
            ext_start = name.index(".config.js")
            return name[:ext_start] or None
        except IndexError:
            return None

    @Validate
    def validate(self, _: "BundleContext") -> None:
        """
        Component validated
        """
        if not self._conf_folder:
            # ./conf is the default configuration folder
            self._conf_folder = os.path.join(os.getcwd(), "conf")

        # Make the folders if necessary
        if not os.path.exists(self._conf_folder):
            os.makedirs(self._conf_folder)

        # Set the folder watcher property
        self._watched_folder = self._conf_folder

    @Invalidate
    def invalidate(self, _: "BundleContext") -> None:
        """
        Component invalidated
        """
        # Clear the cache
        self._watched_folder = ""
        self._conf_folder = ""

    def __load_file(self, filename: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Loads the configuration file with the given name

        :param filename: A simple file name
        :return: A tuple (PID, properties) or None
        """
        pid = self._get_pid(filename)
        if not pid:
            # Not a configuration file
            return None

        try:
            # Load the properties
            properties = self.load(pid)
        except IOError as ex:
            # Can't read file
            _logger.error("Error reading %s: %s", filename, ex)
            return None
        except ValueError as ex:
            # Bad JSON file
            _logger.error("Error parsing %s: %s", filename, ex)
            return None

        return pid, properties

    def exists(self, pid: str) -> bool:
        """
        Returns True if a configuration with the given PID exists

        :param pid: PID of a configuration
        :return: True if a readable configuration exists
        """
        return os.path.isfile(self._get_file(pid))

    def load(self, pid: str) -> Dict[str, Any]:
        """
        Loads the configuration file for the given PID

        :param pid: A configuration PID
        :return: The properties in the configuration file
        :raise IOError: File not found/readable
        :raise ValueError: Invalid file content
        """
        with open(self._get_file(pid), "r") as filep:
            data = filep.read()

        # Store the configuration
        return cast(Dict[str, Any], json.loads(data))

    def store(self, pid: str, properties: Dict[str, Any]) -> None:
        """
        Stores the configuration with the given PID. Overwrites existing
        configuration.

        :param pid: A configuration PID
        :param properties: Configuration values
        :raise IOError: File not writable
        """
        # Write to the file
        with open(self._get_file(pid), "w") as filep:
            # Write the JSON data
            filep.write(json.dumps(properties, sort_keys=True, indent=4, separators=(",", ": ")))
            # Be nice, add a line feed
            filep.write("\n")

    def delete(self, pid: str) -> bool:
        """
        Removes the configuration for the given PID. Does nothing if the
        configuration does not exist.

        :param pid: A configuration PID
        :return: True if the file has been successfully removed, else False
        """
        try:
            os.remove(self._get_file(pid))
            return True
        except OSError:
            return False

    def get_pids(self) -> Iterable[str]:
        """
        Returns the list of PIDs this storage could read
        """
        pids: Set[str] = set()
        for filename in os.listdir(self._conf_folder):
            if os.path.isfile(os.path.join(self._conf_folder, filename)):
                pid = self._get_pid(filename)
                if pid:
                    pids.add(pid)
        return pids

    def folder_change(self, folder: str, added: List[str], updated: List[str], deleted: List[str]) -> None:
        """
        The configuration folder has been modified

        :param folder: Modified folder
        :param added: List of added files
        :param updated: List of modified files
        :param deleted: List of deleted files
        """
        # Check that the folder is really ours
        if folder != self._conf_folder:
            return

        # Handle deleted configurations first
        for filename in deleted:
            pid = self._get_pid(filename)
            if pid:
                try:
                    # Delete the configuration
                    self._directory.delete(pid)
                except KeyError:
                    # Ignore unknown configuration
                    pass

        # Handle updated configurations
        for filenames in added, updated:
            for filename in filenames:
                pid_props = self.__load_file(filename)
                if pid_props is None:
                    # File not readable
                    continue

                pid, properties = pid_props
                try:
                    try:
                        # Update the configuration
                        self._directory.update(pid, properties)
                    except KeyError:
                        # Configuration does not exist yet, create it
                        self._directory.add(pid, properties, self)
                except (KeyError, ValueError, IOError) as ex:
                    # Log other errors
                    _logger.error("Error updating %s: %s", pid, ex)


@pelix.constants.BundleActivator
class Activator(pelix.constants.ActivatorProto):
    """
    Instantiates the default JSON configuration provider
    """

    def start(self, context: "BundleContext") -> None:
        """
        Bundle started
        """
        if context.get_property(services.FRAMEWORK_PROP_CONFIGADMIN_DISABLE_DEFAULT_PERSISTENCE):
            # No need to run the default provider
            return

        # Small trick to add a late Instantiate decoration
        # to the component factory
        Instantiate("pelix-services-configuration-json-default")(JsonPersistence)

    def stop(self, context: "BundleContext") -> None:
        """
        Bundle stopped
        """
        ...
