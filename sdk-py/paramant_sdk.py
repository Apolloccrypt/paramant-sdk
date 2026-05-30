"""Deprecated import shim.

The implementation moved into the ``paramant`` package in 3.2.0. Importing from
``paramant_sdk`` still works but is deprecated and will be removed in 4.0. Use
``from paramant import GhostPipe`` instead.
"""
import warnings as _warnings

from paramant import *  # noqa: F401,F403  (re-exports the package public surface)
from paramant import __version__  # noqa: F401
from paramant.client import _zero, _secret, _canonical_sign_input  # noqa: F401

_warnings.warn(
    "Importing from 'paramant_sdk' is deprecated; use 'from paramant import ...'. "
    "The 'paramant_sdk' shim will be removed in 4.0.",
    DeprecationWarning,
    stacklevel=2,
)
