import time
import pytest
from watchdog.events import FileSystemEvent

from file_transfer.file_transfer import FileTransfer


def test_start_leads_to_correct_state(file_transfer: FileTransfer) -> None:
    # given
    ft = file_transfer

    # when
    ft.start()

    # then
    assert ft.running
    assert ft.observer.is_alive


def test_stop_leads_to_correct_state(file_transfer: FileTransfer) -> None:
    # given
    ft = file_transfer
    ft.start()

    # when
    ft.stop()

    # then
    assert not ft.running
    buffer_sec = 5.0
    deadline = time.time() + buffer_sec
    while ft.observer.is_alive() and time.time() < deadline:
        time.sleep(0.2)

    assert not ft.observer.is_alive(), (
        f"Observer did not shut down within {buffer_sec} seconds"
    )


@pytest.mark.parametrize(
    "filename,expected_skip",
    [
        ("some_file.txt", True),
        ("some_file.mp3", False),
    ],
)
def test_on_any_event_filters_extensions_correctly(
    file_transfer: FileTransfer,
    filename: str,
    expected_skip: bool,
) -> None:
    # given
    ft = file_transfer
    event = FileSystemEvent(src_path=filename)

    # when
    ft.on_any_event(event)

    # then
    assert ft._skip_specific_handler == expected_skip


@pytest.mark.parametrize(
    "filename,expected_skip",
    [
        (".DS_Store", True),
        ("some_file.wav", False),
    ],
)
def test_on_any_event_sets_skip_flag_correctly(
    file_transfer: FileTransfer,
    filename: str,
    expected_skip: bool,
) -> None:
    # given
    ft = file_transfer
    event = FileSystemEvent(src_path=filename)

    # when
    ft.on_any_event(event)

    # then
    assert ft._skip_specific_handler == expected_skip
