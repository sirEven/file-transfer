from pathlib import Path
from typing import List

from watchdog.events import FileSystemEventHandler, FileSystemEvent
import shutil
import os
import subprocess
from watchdog.observers import Observer
from watchdog.observers.api import EventDispatcher
import logging
import queue
import threading
import time
from dotenv import load_dotenv

from file_transfer.config import load_config

# TODO: Rewrite this script "in maintainable" 🦾🤖...
# TODO: Implement recursive folder handling (if not yet covered by watchdog)
# TODO: Make bigger files work as well - e.g.: Podcasts.
# Load environment variables

load_dotenv()
# Remote Host & User
DEST_HOST = os.getenv("DEST_HOST")
DEST_USER = os.getenv("DEST_USER")


class FileTransfer(FileSystemEventHandler):
    def __init__(self, config_file: str = "config.json"):

        # Configuration
        config = load_config(Path(config_file))
        self._source_dir = config.get("source_dir")
        self._ignored_files = config.get("ignored_files")
        if transferred_dir := config.get("transferred_dir"):
            self._transferred_path = Path(transferred_dir)
            if not self._transferred_path.exists():
                self._transferred_path.mkdir(parents=True, exist_ok=True)
        self._valid_ext = config.get("valid_extensions")
        self._dest_dir = config.get("dest_dir")

        # Debug & logging
        self._debug = config.get("debug")
        logging.basicConfig(
            filename=config.get("log_file"),
            level=logging.INFO if self._debug else logging.CRITICAL,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )
        self._logger = logging.getLogger()

        assert self._source_dir
        self.observer = Observer()
        self.observer.schedule(self, self._source_dir, recursive=False)
        self.file_queue: queue.Queue[Path] = queue.Queue()
        self.queued_files: set[Path] = set()  # Track files already in queue
        self.processed_files: set[Path] = (
            set()
        )  # Track fully processed (transferred) files
        self.running = False
        self.transfer_lock = threading.Lock()  # Lock for transfer_file
        self.queue_lock = threading.Lock()  # Lock for queue operations
        self._skip_specific_handler = False

    def start(self):
        self.running = True
        self.observer.start()
        # Start queue processing thread
        self.queue_thread = threading.Thread(target=self.process_queue, daemon=True)
        self.queue_thread.start()
        if self._debug:
            self._logger.info("Starting file transfer daemon")

    def stop(self):
        self.running = False
        # Stop observer and unschedule all events
        try:
            self.observer.unschedule_all()
            self.observer.stop()
            self.observer.event_queue.put(EventDispatcher.stop_event)
        except Exception as e:
            if self._debug:
                self._logger.error(f"Error stopping observer: {str(e)}")
        # Clear queue and sets
        with self.queue_lock:
            while not self.file_queue.empty():
                try:
                    self.file_queue.get_nowait()
                    self.file_queue.task_done()
                except queue.Empty:
                    break
            self.queued_files.clear()
            self.processed_files.clear()
        try:
            self.observer.join(timeout=5.0)
            self.queue_thread.join(timeout=5.0)
        except Exception as e:
            if self._debug:
                self._logger.error(f"Error joining threads: {str(e)}")
        if self._debug:
            self._logger.info("Stopping file transfer daemon")

    def on_any_event(self, event: FileSystemEvent):
        if event.is_directory:
            self._skip_specific_handler = True
            if self._debug:
                self._logger.info(
                    f"Skipped file (part of ignore list): {event.src_path}"
                )
            return

        assert self._ignored_files
        if os.path.basename(event.src_path) in self._ignored_files:
            self._skip_specific_handler = True
            if self._debug:
                self._logger.info(
                    f"Skipped file (part of ignore list): {event.src_path}"
                )
            return

        assert self._transferred_path
        # Check if file was already transferred (exists in transferred_dir)
        transferred_file = self._transferred_path / Path(str(event.src_path)).name
        if transferred_file.exists():
            self._skip_specific_handler = True
            if self._debug:
                self._logger.info(
                    f"Skipped file (already transferred): {event.src_path}"
                )
            return

        assert self._valid_ext
        ext = Path(str(event.src_path)).suffix.lower()

        if ext not in self._valid_ext:
            self._skip_specific_handler = True
            if self._debug:
                self._logger.info(f"Skipped file (invalid extension): {event.src_path}")
            return

        self._skip_specific_handler = False

        if self._debug:
            self._logger.info(
                f"Event detected: type={event.event_type}, path={event.src_path}, is_directory={event.is_directory}"
            )

    def on_created(self, event: FileSystemEvent):
        if self._skip_specific_handler:
            return

        # Deduplicate before adding to queue (after created, the source should not be in queue already)
        with self.queue_lock:
            if Path(str(event.src_path)) in self.queued_files:
                if self._debug:
                    self._logger.info(
                        f"Skipped duplicate queue attempt: {event.src_path}"
                    )
            else:
                self.queued_files.add(Path(str(event.src_path)))
                self.file_queue.put(Path(str(event.src_path)))
                if self._debug:
                    self._logger.info(f"Queued file for processing: {event.src_path}")

    def on_moved(self, event: FileSystemEvent):
        if self._skip_specific_handler:
            return

        # Deduplicate before adding to queue (after move the destination should not be in queue already)
        with self.queue_lock:
            if Path(str(event.dest_path)) in self.queued_files:
                if self._debug:
                    self._logger.info(
                        f"Skipped duplicate queue attempt for renamed file: {event.dest_path}"
                    )
            else:
                self.queued_files.add(Path(str(event.dest_path)))
                self.file_queue.put(Path(str(event.dest_path)))
                if self._debug:
                    self._logger.info(
                        f"Queued renamed file for processing: {event.dest_path}"
                    )

    def process_queue(self):
        while self.running:
            try:
                # Get next file from queue (block until one is available)
                with self.queue_lock:
                    file_path = self.file_queue.get(timeout=1)
                    if self._debug:
                        self._logger.info(f"Dequeued file for processing: {file_path}")
                    if file_path in self.processed_files:
                        if self._debug:
                            self._logger.info(
                                f"File already transferred, skipping: {file_path}"
                            )
                        self.file_queue.task_done()
                        continue
                    if file_path not in self.queued_files:
                        if self._debug:
                            self._logger.info(
                                f"File no longer in queued set, skipping: {file_path}"
                            )
                        self.file_queue.task_done()
                        continue
                try:
                    self.transfer_file(file_path)
                finally:
                    with self.queue_lock:
                        if self._debug:
                            self._logger.info(f"Marking task done for: {file_path}")
                        self.queued_files.discard(file_path)
                        self.processed_files.add(file_path)
                        self.file_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                if self._debug:
                    self._logger.error(f"Error in queue processing: {str(e)}")

    def transfer_file(self, file_path: Path):
        with self.transfer_lock:  # Ensure exclusive execution
            try:
                if file_path in self.processed_files:
                    if self._debug:
                        self._logger.info(
                            f"File already transferred, skipping: {file_path}"
                        )
                    return
                # Check if file still exists
                if not os.path.exists(file_path):
                    if self._debug:
                        self._logger.info(
                            f"File already transferred or removed: {file_path}"
                        )
                    return

                # Wait for file stability (size stops changing)
                # TODO: Replace with proper stability check at some point (e.g. file extension).
                if self._debug:
                    self._logger.info(f"Checking stability for: {file_path}")
                previous_size = -1
                for _ in range(3):  # Check 3 times, 1 second apart
                    current_size = os.stat(file_path).st_size
                    if current_size == previous_size:
                        break
                    previous_size = current_size
                    time.sleep(1)
                else:
                    if self._debug:
                        self._logger.info(f"File still unstable, skipping: {file_path}")
                    return

                if self._debug:
                    self._logger.info(f"File stable: {file_path}")

                # Log file attributes
                if self._debug:
                    file_stats = os.stat(file_path)
                    self._logger.info(
                        f"Transferring file: path={file_path}, size={file_stats.st_size} bytes, "
                        f"mtime={time.ctime(file_stats.st_mtime)}"
                    )

                # Transfer file to remote destination with retries
                max_retries = 3
                retry_delay = 5  # seconds
                for attempt in range(max_retries):
                    if self._debug:
                        self._logger.info(
                            f"Executing SCP command for: {file_path} (attempt {attempt + 1}/{max_retries})"
                        )
                    scp_command: List[str | Path] = [
                        "scp",
                        "-o",
                        "StrictHostKeyChecking=no",
                        file_path,
                        f"{DEST_USER}@{DEST_HOST}:{self._dest_dir}",
                    ]
                    process = subprocess.Popen(
                        scp_command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    returncode = process.wait()
                    assert process.stderr
                    stderr_output = process.stderr.read()
                    if returncode == 0:
                        print()  # Newline after progress bar
                        if self._debug:
                            self._logger.info(
                                f"SCP completed for: {file_path}, returncode={returncode}"
                            )
                        break  # Success, exit retry loop
                    else:
                        if self._debug:
                            self._logger.error(
                                f"SCP failed for {file_path} on attempt {attempt + 1}: returncode={returncode}, stderr={stderr_output.strip()}"
                            )
                        if attempt < max_retries - 1:
                            if self._debug:
                                self._logger.info(
                                    f"Retrying SCP for {file_path} in {retry_delay} seconds..."
                                )
                            time.sleep(retry_delay)
                        else:
                            raise subprocess.CalledProcessError(
                                returncode, scp_command, stderr_output
                            )

                # Move file to transferred folder
                if self._debug:
                    self._logger.info(f"Moving file to transferred: {file_path}")
                os.makedirs(Path(str(self._transferred_path)), exist_ok=True)
                transferred_path = os.path.join(
                    str(self._transferred_path), os.path.basename(file_path)
                )
                shutil.move(file_path, transferred_path)
                if self._debug:
                    self._logger.info(f"Moved {file_path} to {transferred_path}")
            except Exception as e:
                if self._debug:
                    self._logger.error(f"Error processing {file_path}: {str(e)}")
