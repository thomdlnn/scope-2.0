from .base import Source
from .depots import DepotsSource
from .reports import ReportsResult, ReportsSource

#: Sources actives, dans l'ordre de collecte.
SOURCES: list[Source] = [DepotsSource(), ReportsSource()]

__all__ = ["SOURCES", "Source", "DepotsSource", "ReportsSource", "ReportsResult"]
