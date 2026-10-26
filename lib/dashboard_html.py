"""HTML dashboard renderer (build_dashboard + helpers).

Split into the lib/dashboard/ sub-package; this module re-exports the
public API for backward compatibility (lib/runners.py imports it).
"""
from .dashboard import build_dashboard  # noqa: F401

__all__ = ['build_dashboard']
