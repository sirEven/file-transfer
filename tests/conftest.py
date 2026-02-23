from pathlib import Path
from typing import Any, Dict, Generator
import json
import pytest

from file_transfer.file_transfer import FileTransfer


@pytest.fixture
def test_config(tmp_path: Path) -> Generator[Path, None, None]:
    config_data: Dict[str, Any] = {
        "source_dir": str(tmp_path / "source"),
        "dest_dir": str(tmp_path / "dest"),
        "transferred_dir": str(tmp_path / "transferred"),
        "log_file": str(tmp_path / "log.log"),
        "valid_extensions": [".mp3", ".wav"],
        "ignored_files": [".DS_Store"],
        "debug": True,
    }

    config_file = tmp_path / "config.json"
    with open(config_file, "w") as f:
        json.dump(config_data, f)
    yield config_file


@pytest.fixture
def file_transfer(test_config: Path) -> Generator[FileTransfer, None, None]:
    ft = FileTransfer()
    yield ft
    ft.stop()
