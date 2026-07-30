"""The load manifest: importing this module registers every collector.

This list used to live in ``collectors/__init__.py``. It moved because the
package's ``__init__`` runs whenever *any* collector is imported — so a build
that wants only a few of them (``qualifier.SCOPE``) could not avoid dragging in
all seventeen, and "this binary cannot read your serial numbers" would have been
a claim about behaviour rather than about the artifact.

Keeping the manifest in its own module makes the set of collectors a **choice
the entry point makes**: import this for everything, or import the handful you
need. The registry imports this one; nothing else has to change (ADR-002 still
holds — collectors self-register at import, this is only *where the imports
live*). See ADR-021.
"""

from . import (  # noqa: F401  (imported for the side effect of registering)
    audio,
    baseboard,
    battery,
    bluetooth,
    cpu,
    disk,
    gpu,
    input_devices,
    llm_runtime,
    memory,
    memory_modules,
    monitors,
    network,
    printers,
    storage_devices,
    system,
    usb,
)
