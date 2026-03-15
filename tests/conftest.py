from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def isolated_db_path():
    db_path = Path(__file__).resolve().parents[1] / "tmp" / f"test-{uuid4().hex}.db"
    yield db_path

    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{db_path}{suffix}")
        if candidate.exists():
            candidate.unlink()
