"""Verso -- a document firewall that inspects a PDF before an AI agent reads it."""

__version__ = "0.4.1"

from .scan import ScanResult, scan

__all__ = ["scan", "ScanResult", "__version__"]
