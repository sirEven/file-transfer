from pathlib import Path
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


def test_on_any_event_skips_directories(file_transfer: FileTransfer) -> None:
    # given
    ft = file_transfer
    event = FileSystemEvent("source_path")
    event.is_directory = True

    # when
    ft.on_any_event(event)

    # then
    assert ft._skip_specific_handler


@pytest.mark.parametrize(
    "filename,expected_skip",
    [
        ("some_file.txt", True),
        ("some_file.mp3", False),
    ],
)
def test_on_any_event_skips_invalid_extensions_correctly(
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
def test_on_any_event_skips_ignored_files_correctly(
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


def test_on_any_event_skips_already_transferred_files_correctly(
    file_transfer: FileTransfer,
    tmp_path: Path,
) -> None:
    # given
    ft = file_transfer
    transferred_dir = tmp_path / "transferred"
    fake_transferred_file = transferred_dir / "already_transferred.mp3"
    fake_transferred_file.touch()

    event = FileSystemEvent(src_path=str(fake_transferred_file))

    # when
    ft.on_any_event(event)

    # then
    assert ft._skip_specific_handler


def test_on_created_skips_already_queued_file(file_transfer: FileTransfer) -> None:
    # given
    src_path = "some_silly_path"
    ft = file_transfer
    ft.queued_files.add(Path(src_path))
    event = FileSystemEvent(src_path=src_path)

    # when
    ft.on_created(event)

    # then
    assert ft.file_queue.empty


def test_on_moved_skips_already_queued_file(file_transfer: FileTransfer) -> None:
    # given
    src_path = "some_silly_path"
    dest_path = "some_crazy_dest_path"
    ft = file_transfer
    ft.queued_files.add(Path(dest_path))
    event = FileSystemEvent(src_path=src_path, dest_path=dest_path)

    # when
    ft.on_moved(event)

    # then
    assert ft.file_queue.empty
