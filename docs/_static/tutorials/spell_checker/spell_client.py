#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
This bundle defines a component that consumes a spell checker.
It provides a shell command service, registering a "spell" command that can be
used in the shell of Pelix.

It uses a dictionary service to check for the proper spelling of a word by check
for its existence in the dictionary.
"""

from spell_checker_api import SpellChecker

from pelix.framework import BundleContext
from pelix.ipopo.decorators import ComponentFactory, Instantiate, Invalidate, Provides, Requires, Validate
from pelix.shell import ShellCommandsProvider
from pelix.shell.beans import ShellSession


# Name the component factory
@ComponentFactory("spell_client_factory")
# Consume a single Spell Checker service
@Requires("_spell_checker", SpellChecker)
# Provide a shell command service
@Provides(ShellCommandsProvider)
# Automatic instantiation
@Instantiate("spell_client_instance")
class SpellClient(ShellCommandsProvider):
    """
    A component that provides a shell command (spell.spell), using a
    Spell Checker service.
    """

    # Declare the injected field with its type
    _spell_checker: SpellChecker

    @Validate
    def validate(self, context: BundleContext) -> None:
        """
        Component validated, just print a trace to visualize the event.
        Between this call and the call to invalidate, the _spell_checker member
        will point to a valid spell checker service.
        """
        print("A client for spell checker has been started")

    @Invalidate
    def invalidate(self, context: BundleContext) -> None:
        """
        Component invalidated, just print a trace to visualize the event
        """
        print("A spell client has been stopped")

    def get_namespace(self):
        """
        Retrieves the name space of this shell command provider.
        Look at the shell tutorial for more information.
        """
        return "spell"

    def get_methods(self):
        """
        Retrieves the list of (command, method) tuples for all shell commands
        provided by this component.
        Look at the shell tutorial for more information.
        """
        return [("spell", self.spell)]

    def spell(self, session: ShellSession):
        """
        Reads words from the standard input and checks for their existence
        from the selected dictionary.

        :param session: The shell session, a bean to interact with the user
        """
        # Request the language of the text to the user
        passage = None
        language = session.prompt("Please enter your language, EN or FR: ")
        language = language.upper()

        while passage != "quit":
            # Request the text to check
            passage = session.prompt("Please enter your paragraph, or 'quit' to exit:\n")

            if passage and passage != "quit":
                # A text has been given: call the spell checker, which have been
                # injected by iPOPO.
                misspelled_words = self._spell_checker.check(passage, language)
                if not misspelled_words:
                    session.write_line("All words are well spelled!")
                else:
                    session.write_line(f"The misspelled words are: {misspelled_words}")
