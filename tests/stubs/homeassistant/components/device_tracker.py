from enum import Enum

class SourceType(Enum):
    GPS = "gps"

# keep compatibility for imports that expect attributes at module level
GPS = SourceType.GPS


class TrackerEntity:
    """Minimal TrackerEntity stub for tests."""

    @property
    def latitude(self):
        return None

    @property
    def longitude(self):
        return None

    @property
    def source_type(self):
        return None
