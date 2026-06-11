"""Collector modules.

Importing this package imports every collector module, which is what makes the
``@register`` decorators run. Add a new collector by creating a module here and
listing it below — nothing else in the codebase needs to change.
"""

from . import (  # noqa: F401  (imported for the side effect of registering)
    system,
    cpu,
    memory,
    disk,
    network,
    gpu,
    baseboard,
    memory_modules,
    storage_devices,
    usb,
    monitors,
    audio,
    input_devices,
    battery,
    bluetooth,
    printers,
)
