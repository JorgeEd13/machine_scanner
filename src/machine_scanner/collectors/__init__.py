"""Collector modules — one per topic.

Add a new collector by creating a module here and listing it in ``_all.py``, the
load manifest. Nothing else in the codebase changes.

**This package deliberately imports nothing.** A package's ``__init__`` runs
whenever any of its submodules is imported, so keeping the manifest here would
make "load one collector" and "load all seventeen" the same act — and the
requirements checker (``qualifier.py``) exists precisely to load five. See
ADR-021.
"""
