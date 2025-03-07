#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Test package for Pelix

:author: Thomas Calmant
"""

import logging


def log_on() -> None:
    """
    Enables the logging
    """
    logging.disable(logging.NOTSET)


def log_off() -> None:
    """
    Disables the logging
    """
    logging.disable(logging.CRITICAL)
