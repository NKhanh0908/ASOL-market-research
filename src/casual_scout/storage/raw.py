from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


class RawStore:
    """Content-addressed storage for immutable HTTP response bodies."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def put(self, body: bytes) -> tuple[str, Path]:
        digest = hashlib.sha256(body).hexdigest()
        directory = self.root / digest[:2]
        target = directory / digest
        directory.mkdir(parents=True, exist_ok=True)

        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{digest}.", dir=directory)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())

            if target.exists():
                if target.read_bytes() != body:
                    raise RuntimeError(
                        f"raw evidence hash {digest} already contains different content"
                    )
                return digest, target

            os.replace(temporary, target)
            return digest, target
        finally:
            temporary.unlink(missing_ok=True)
