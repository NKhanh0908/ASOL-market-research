from dataclasses import dataclass
from pathlib import Path


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
