from pathlib import Path
import time
import pytest
import unittest.mock as mock
from watchdog.events import FileSystemEvent

from file_transfer.file_transfer import FileTransfer


def test_start_leads_to_correct_state(file_transfer: FileTransfer) -> None:
    # given
    ft = file_transfer

    # when
    ft.start()

    # then
    assert ft._running
    assert ft._observer.is_alive


def test_stop_leads_to_correct_state(file_transfer: FileTransfer) -> None:
    # given
    ft = file_transfer
    ft.start()

    # when
    ft.stop()

    # then
    assert not ft._running
    buffer_sec = 5.0
    deadline = time.time() + buffer_sec
    while ft._observer.is_alive() and time.time() < deadline:
        time.sleep(0.2)

    assert not ft._observer.is_alive(), (
        f"Observer did not shut down within {buffer_sec} seconds"
    )


def test_on_any_event_skips_directories(file_transfer: FileTransfer) -> None:
    # given
    ft = file_transfer
    event = FileSystemEvent("source_path")
    event.is_directory = True

    # when on_any_event and then an additional handler is called, it skips execution
    ft.on_any_event(event)
    ft.on_created(event)

    # then
    assert ft._file_queue.empty()


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

    # when on_any_event and then an additional handler is called, it skips execution
    ft.on_any_event(event)
    ft.on_created(event)

    # then
    assert ft._file_queue.empty() == expected_skip


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

    # when on_any_event and then an additional handler is called, it skips execution
    ft.on_any_event(event)
    ft.on_created(event)

    # then
    assert ft._file_queue.empty() == expected_skip


@pytest.mark.parametrize(
    "filename,expected_skip",
    [
        ("already_transferred.mp3", True),
        ("some_file.wav", False),
    ],
)
def test_on_any_event_skips_already_transferred_files_correctly(
    file_transfer: FileTransfer,
    filename: str,
    expected_skip: bool,
    tmp_path: Path,
) -> None:
    # given
    ft = file_transfer
    transferred_dir = tmp_path / "transferred"
    fake_transferred_file = transferred_dir / "already_transferred.mp3"
    fake_transferred_file.touch()

    event = FileSystemEvent(src_path=filename)

    # when on_any_event and then an additional handler is called, it skips execution
    ft.on_any_event(event)
    ft.on_created(event)

    # then
    assert ft._file_queue.empty() == expected_skip


@pytest.mark.parametrize(
    "filename,queue_expected_empty",
    [
        ("already_queued.mp3", True),
        ("some_file.wav", False),
    ],
)
def test_on_created_skips_already_queued_file(
    file_transfer: FileTransfer,
    filename: str,
    queue_expected_empty: bool,
) -> None:
    # given
    src_path = filename
    ft = file_transfer
    ft._queued_files.add(Path("already_queued.mp3"))
    event = FileSystemEvent(src_path=src_path)

    # when
    ft.on_created(event)

    # then
    assert ft._file_queue.empty() == queue_expected_empty


@pytest.mark.parametrize(
    "filename,queue_expected_empty",
    [
        ("already_queued.mp3", True),
        ("some_file.wav", False),
    ],
)
def test_on_moved_skips_already_queued_file(
    file_transfer: FileTransfer,
    filename: str,
    queue_expected_empty: bool,
) -> None:
    # given
    src_path = "some_silly_path"
    dest_path = filename
    ft = file_transfer
    ft._queued_files.add(Path("already_queued.mp3"))
    event = FileSystemEvent(src_path=src_path, dest_path=dest_path)

    # when
    ft.on_moved(event)

    # then
    assert ft._file_queue.empty() == queue_expected_empty


def test_transfer_file_skips_already_processed_file(
    file_transfer: FileTransfer,
) -> None:
    # given
    ft = file_transfer
    file_path = Path(ft._source_dir) / "some_file.mp3"
    file_path.touch()  # Create the file so os.stat works
    ft._processed_files.add(file_path)

    # when
    with (
        mock.patch("subprocess.Popen") as mock_popen,
        mock.patch("shutil.move") as mock_move,
    ):
        ft.transfer_file(file_path)

    # then
    mock_popen.assert_not_called()
    mock_move.assert_not_called()


def test_transfer_file_handles_non_processed_file(
    file_transfer: FileTransfer,
) -> None:
    # given
    ft = file_transfer
    file_path = Path(ft._source_dir) / "some_file.mp3"
    second_file_path = Path(ft._source_dir) / "some_other_file.mp3"
    file_path.touch()  # Create the file so os.stat works
    second_file_path.touch()
    ft._processed_files.add(file_path)

    # when
    with (
        mock.patch("subprocess.Popen") as mock_popen,
        mock.patch("shutil.move") as mock_move,
        mock.patch("time.sleep"),
    ):
        # Configure mock to succeed
        mock_popen.return_value.wait.return_value = 0
        mock_popen.return_value.stderr.read.return_value = ""
        ft.transfer_file(second_file_path)

    # then
    mock_popen.assert_called()
    mock_move.assert_called()
