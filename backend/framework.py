"""Load pinned framework modules without hardcoded layout or sys.path changes."""

import hashlib
import importlib.util
import sys
from threading import RLock

_lock = RLock()


def load_module(settings, filename):
    path = settings.tool_path(filename).resolve()
    name = "bbasm_vendor_" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
    with _lock:
        if name not in sys.modules:
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:
                raise RuntimeError(f"Cannot load framework module: {filename}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module  # dataclasses consult sys.modules during import.
            try:
                spec.loader.exec_module(module)
            except Exception:
                sys.modules.pop(name, None)
                raise
        return sys.modules[name]
