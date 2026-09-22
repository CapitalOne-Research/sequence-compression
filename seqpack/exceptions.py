"""Public exception hierarchy for seqpack.

All errors raised by seqpack's public API derive from `SeqPackError`, so
callers who want to catch "anything seqpack-specific" have a single type to
catch. Each concrete exception also multiply-inherits from the matching
builtin (`TypeError`/`ValueError`) that earlier versions of seqpack raised
directly, so existing `except ValueError`/`except TypeError` call sites keep
working unchanged.
"""

from __future__ import annotations


class SeqPackError(Exception):
    """Base class for all errors raised by seqpack's public API."""


class InvalidInputError(SeqPackError, TypeError):
    """Raised when a public function receives an argument of the wrong shape or type."""


class UnknownSchemeError(SeqPackError, ValueError):
    """Raised when a pipeline references a step that isn't a registered scheme."""


class DecodingError(SeqPackError, ValueError):
    """Raised when a wire-format record can't be parsed or decoded."""
