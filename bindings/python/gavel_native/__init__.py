"""Official Python binding for the gavel native core.

Wraps the compiled C library (``core/gavel.c``) behind the same signatures the
pure-Python reference exposes, so a consumer can swap one import for the other.
The binding owns exactly the FFI mechanics — locating symbols, mapping Python
values onto C types and back. Decision logic lives in the core; conformance is
decided by the vectors in ``vectors/``.
"""

from gavel_native.core import GavelCore

__all__ = ["GavelCore"]
