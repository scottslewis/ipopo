#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
This bundle provides a component that is a simple implementation of the
Dictionary service. It contains some English words.
"""

from typing import Set

from spell_checker_api import SpellDictionary

from pelix.framework import BundleContext
from pelix.ipopo.decorators import ComponentFactory, Instantiate, Invalidate, Property, Provides, Validate


# Name the iPOPO component factory
@ComponentFactory("spell_dictionary_en_factory")
# This component provides a dictionary service
@Provides(SpellDictionary)
# It is the English dictionary
@Property("_language", "language", "EN")
# Automatically instantiate a component when this factory is loaded
@Instantiate("spell_dictionary_en_instance")
class EnglishSpellDictionary(SpellDictionary):
    """
    Implementation of a spell dictionary, for English language.
    """

    def __init__(self) -> None:
        """
        Declares members, to respect PEP-8.
        """
        self.dictionary: Set[str] = set()

    @Validate
    def validate(self, context: BundleContext) -> None:
        """
        The component is validated. This method is called right before the
        provided service is registered to the framework.
        """
        # All setup should be done here
        self.dictionary = {"hello", "world", "welcome", "to", "the", "ipopo", "tutorial"}
        print("An English dictionary has been added")

    @Invalidate
    def invalidate(self, context: BundleContext) -> None:
        """
        The component has been invalidated. This method is called right after
        the provided service has been removed from the framework.
        """
        self.dictionary = set()

    # No need to have explicit types: annotations are inherited
    def check_word(self, word):
        word = word.lower().strip()
        return not word or word in self.dictionary
