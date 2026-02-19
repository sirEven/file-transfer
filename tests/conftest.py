from typing import Generator

import pytest

from file_transfer.file_transfer import FileTransfer


@pytest.fixture
def file_transfer() -> Generator[FileTransfer, None, None]:
    ft = FileTransfer()
    yield ft
    ft.stop()
