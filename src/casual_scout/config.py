from dataclasses import dataclass
from pathlib import Path

# Shared iOS button/schedule scope; data-view filters and Android stay independent.
IOS_COLLECTION_COUNTRIES = ('vn', 'th', 'id', 'my', 'ph', 'sg', 'la', 'kh', 'us')
IOS_COLLECTION_SCOPE = 'nearby-us'
IOS_COLLECTION_LABEL = 'Việt Nam, Thái Lan, Indonesia, Malaysia, Philippines, Singapore, Lào, Campuchia, Mỹ'


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    request_interval: float = 4.0
    timeout: float = 20.0
    attempts: int = 3

    @property
    def database_path(self) -> Path:
        return self.data_dir / "casual-scout.sqlite3"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"
