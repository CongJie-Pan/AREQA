"""Domain services with lazy legacy imports and the shared application namespace.

Keep providers and workers out of package initialization. The additional service
root also participates when application bootstrap adds it to sys.path later.
"""

from pathlib import Path as _Path
from pkgutil import extend_path as _extend_path

__path__ = _extend_path(__path__, __name__)
_shared_services = _Path(__file__).resolve().parents[2] / "src/main/python/services"
if _shared_services.is_dir() and str(_shared_services) not in __path__:
    __path__.append(str(_shared_services))
__path__.append(str(_Path(__file__).with_name("_compat")))
