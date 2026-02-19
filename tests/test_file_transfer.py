import time

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
    ft = file_transfer
    ft.start()

    ft.stop()

    assert not ft.running

    deadline = time.time() + 5.0
    while ft.observer.is_alive() and time.time() < deadline:
        time.sleep(0.2)

    assert not ft.observer.is_alive(), "Observer did not shut down within 12 seconds"
