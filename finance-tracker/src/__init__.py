import importlib
import sys
from types import ModuleType


class _ReimportPackage(ModuleType):
    def __getattribute__(self, name):
        if not name.startswith("_"):
            full = f"{ModuleType.__getattribute__(self, '__name__')}.{name}"
            if full in sys.modules:
                return sys.modules[full]
            try:
                attr = ModuleType.__getattribute__(self, name)
            except AttributeError:
                attr = None
            if attr is not None and isinstance(attr, ModuleType) and attr.__name__ == full:
                return importlib.import_module(full)
        return ModuleType.__getattribute__(self, name)


sys.modules[__name__].__class__ = _ReimportPackage
