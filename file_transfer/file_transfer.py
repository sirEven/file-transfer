from pathlib import Path
from typing import List

from watchdog.events import FileSystemEventHandler, FileSystemEvent
import shutil
import os
import subprocess
from queue import Queue
from watchdog.observers import Observer
from watchdog.observers.api import EventDispatcher
import logging
import queue
import threading
import time
import re
from dotenv import load_dotenv

# TODO: Rewrite this script "in maintainable" 🦾🤖...
# TODO: Implement recursive folder handling (if not yet covered by watchdog)
# TODO: Make bigger files work as well - e.g.: Podcasts.bb

# Load environment variables
load_dotenv()

# Configuration
SOURCE_DIR = os.getenv("SOURCE_DIR")
DEST_USER = os.getenv("DEST_USER")
DEST_HOST = os.getenv("DEST_HOST")
DEST_DIR = os.getenv("DEST_DIR")
TRANSFERRED_DIR = os.getenv("TRANSFERRED_DIR")
LOG_FILE = os.getenv("LOG_FILE")

# TODO: If this location does not exist, we need to create it here
if LOG_FILE:
    log_path = Path(LOG_FILE)
    log_dir = log_path.parent  # everything except the filename

    if not log_dir.exists():
        log_dir.mkdir(parents=True, exist_ok=True)

VALID_EXTENSIONS = {
    f".{ext.lower()}" for ext in os.getenv("VALID_EXTENSIONS", "").split(",") if ext
}

DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# Set up logging (file only, disabled in production)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO if DEBUG else logging.CRITICAL,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger()


class FileTransfer(FileSystemEventHandler):
    def __init__(self):
        assert SOURCE_DIR
        self.observer = Observer()
        self.observer.schedule(self, SOURCE_DIR, recursive=False)
        self.file_queue: Queue[Path] = Queue()
        self.queued_files: set[Path] = set()  # Track files already in queue
        self.transferred_files: set[Path] = set()  # Track fully transferred files
        self.running = False
        self.transfer_lock = threading.Lock()  # Lock for transfer_file
        self.queue_lock = threading.Lock()  # Lock for queue operations

    def start(self):
        self.running = True
        self.observer.start()
        # Start queue processing thread
        self.queue_thread = threading.Thread(target=self.process_queue, daemon=True)
        self.queue_thread.start()
        if DEBUG:
            logger.info("Starting file transfer daemon")

    def stop(self):
        self.running = False
        # Stop observer and unschedule all events
        try:
            self.observer.unschedule_all()
            self.observer.stop()
            self.observer.event_queue.put(EventDispatcher.stop_event)
        except Exception as e:
            if DEBUG:
                logger.error(f"Error stopping observer: {str(e)}")
        # Clear queue and sets
        with self.queue_lock:
            while not self.file_queue.empty():
                try:
                    self.file_queue.get_nowait()
                    self.file_queue.task_done()
                except queue.Empty:
                    break
            self.queued_files.clear()
            self.transferred_files.clear()
        try:
            self.observer.join(timeout=5.0)
            self.queue_thread.join(timeout=5.0)
        except Exception as e:
            if DEBUG:
                logger.error(f"Error joining threads: {str(e)}")
        if DEBUG:
            logger.info("Stopping file transfer daemon")

    def on_any_event(self, event: FileSystemEvent):
        # Skip logging for .DS_Store and directory events # TODO: We should create a List of ignored extensions ow which .DS_Store is one. Also we need to determine platform and select that list accordingly
        if os.path.basename(event.src_path) == ".DS_Store" or event.is_directory:
            return
        if DEBUG:
            logger.info(
                f"Event detected: type={event.event_type}, path={event.src_path}, is_directory={event.is_directory}"
            )

    def on_created(self, event: FileSystemEvent):
        if event.is_directory or os.path.basename(event.src_path) == ".DS_Store":
            return
        # Ignore files in TRANSFERRED_DIR
        assert TRANSFERRED_DIR
        if Path(str(event.src_path)).is_relative_to(Path(TRANSFERRED_DIR)):
            if DEBUG:
                logger.info(f"Ignored file in transferred directory: {event.src_path}")
            return
        # Check if file has a valid extension
        if os.path.splitext(event.src_path)[1].lower() in VALID_EXTENSIONS:
            if DEBUG:
                logger.info(f"New file detected: {event.src_path}")
            # Deduplicate before adding to queue
            with self.queue_lock:
                if (
                    Path(str(event.src_path)) in self.queued_files
                    or Path(str(event.src_path)) in self.transferred_files
                ):
                    if DEBUG:
                        logger.info(
                            f"Skipped duplicate queue attempt: {event.src_path}"
                        )
                else:
                    self.queued_files.add(Path(str(event.src_path)))
                    self.file_queue.put(Path(str(event.src_path)))
                    if DEBUG:
                        logger.info(f"Queued file for processing: {event.src_path}")
        elif DEBUG:
            logger.info(f"Ignored file with invalid extension: {event.src_path}")

    def on_moved(self, event: FileSystemEvent):
        if event.is_directory or os.path.basename(event.dest_path) == ".DS_Store":
            return
        # Ignore files moved to TRANSFERRED_DIR
        assert TRANSFERRED_DIR
        dest_path_str = str(
            event.dest_path
        )  # TODO: change startswith to is_relative_to as well.
        if Path(dest_path_str).is_relative_to(Path(TRANSFERRED_DIR)):
            if DEBUG:
                logger.info(
                    f"Ignored file moved to transferred directory: {event.dest_path}"
                )
            return
        # Check if the new path has a valid extension
        if os.path.splitext(event.dest_path)[1].lower() in VALID_EXTENSIONS:
            if DEBUG:
                logger.info(
                    f"File renamed to valid file: {event.dest_path} (from {event.src_path})"
                )
            # Deduplicate before adding to queue
            with self.queue_lock:
                if (
                    Path(str(event.dest_path)) in self.queued_files
                    or Path(str(event.dest_path)) in self.transferred_files
                ):
                    if DEBUG:
                        logger.info(
                            f"Skipped duplicate queue attempt for renamed file: {event.dest_path}"
                        )
                else:
                    self.queued_files.add(Path(str(event.dest_path)))
                    self.file_queue.put(Path(str(event.dest_path)))
                    if DEBUG:
                        logger.info(
                            f"Queued renamed file for processing: {event.dest_path}"
                        )
        elif DEBUG:
            logger.info(
                f"Ignored renamed file with invalid extension: {event.dest_path} (from {event.src_path})"
            )

    def process_queue(self):
        while self.running:
            try:
                # Get next file from queue (block until one is available)
                with self.queue_lock:
                    file_path = self.file_queue.get(timeout=1)
                    if DEBUG:
                        logger.info(f"Dequeued file for processing: {file_path}")
                    if file_path in self.transferred_files:
                        if DEBUG:
                            logger.info(
                                f"File already transferred, skipping: {file_path}"
                            )
                        self.file_queue.task_done()
                        continue
                    if file_path not in self.queued_files:
                        if DEBUG:
                            logger.info(
                                f"File no longer in queued set, skipping: {file_path}"
                            )
                        self.file_queue.task_done()
                        continue
                try:
                    self.transfer_file(file_path)
                finally:
                    with self.queue_lock:
                        if DEBUG:
                            logger.info(f"Marking task done for: {file_path}")
                        self.queued_files.discard(file_path)
                        self.transferred_files.add(file_path)
                        self.file_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                if DEBUG:
                    logger.error(f"Error in queue processing: {str(e)}")

    def transfer_file(self, file_path: Path):
        with self.transfer_lock:  # Ensure exclusive execution
            try:
                if file_path in self.transferred_files:
                    if DEBUG:
                        logger.info(f"File already transferred, skipping: {file_path}")
                    return
                # Check if file still exists
                if not os.path.exists(file_path):
                    if DEBUG:
                        logger.info(f"File already transferred or removed: {file_path}")
                    return

                # Wait for file stability (size stops changing)
                # TODO: Replace with proper stability check at some point (e.g. file extension).
                if DEBUG:
                    logger.info(f"Checking stability for: {file_path}")
                previous_size = -1
                for _ in range(3):  # Check 3 times, 1 second apart
                    current_size = os.stat(file_path).st_size
                    if current_size == previous_size:
                        break
                    previous_size = current_size
                    time.sleep(1)
                else:
                    if DEBUG:
                        logger.info(f"File still unstable, skipping: {file_path}")
                    return

                if DEBUG:
                    logger.info(f"File stable: {file_path}")

                # Log file attributes
                if DEBUG:
                    file_stats = os.stat(file_path)
                    logger.info(
                        f"Transferring file: path={file_path}, size={file_stats.st_size} bytes, "
                        f"mtime={time.ctime(file_stats.st_mtime)}"
                    )

                # Transfer file to remote destination with retries
                max_retries = 3
                retry_delay = 5  # seconds
                for attempt in range(max_retries):
                    if DEBUG:
                        logger.info(
                            f"Executing SCP command for: {file_path} (attempt {attempt + 1}/{max_retries})"
                        )
                    scp_command: List[str | Path] = [
                        "scp",
                        "-o",
                        "StrictHostKeyChecking=no",
                        file_path,
                        f"{DEST_USER}@{DEST_HOST}:{DEST_DIR}",
                    ]
                    process = subprocess.Popen(
                        scp_command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    # Stream progress bar to console
                    # FIXME: Currently broken, don't care atm.
                    progress_pattern = re.compile(
                        r"^\S+\s+\d+%\s+\S+\s+\d{2}:\d{2}$"
                    )  # Matches "filename XX% YYYKB/s ZZ:ZZ"
                    while process.poll() is None:
                        assert process.stdout
                        output = process.stdout.readline()
                        if output and progress_pattern.match(output.strip()):
                            print(output.strip(), end="\r")
                    returncode = process.wait()
                    assert process.stderr
                    stderr_output = process.stderr.read()
                    if returncode == 0:
                        print()  # Newline after progress bar
                        if DEBUG:
                            logger.info(
                                f"SCP completed for: {file_path}, returncode={returncode}"
                            )
                        break  # Success, exit retry loop
                    else:
                        if DEBUG:
                            logger.error(
                                f"SCP failed for {file_path} on attempt {attempt + 1}: returncode={returncode}, stderr={stderr_output.strip()}"
                            )
                        if attempt < max_retries - 1:
                            if DEBUG:
                                logger.info(
                                    f"Retrying SCP for {file_path} in {retry_delay} seconds..."
                                )
                            time.sleep(retry_delay)
                        else:
                            raise subprocess.CalledProcessError(
                                returncode, scp_command, stderr_output
                            )

                # Move file to transferred folder
                if DEBUG:
                    logger.info(f"Moving file to transferred: {file_path}")
                os.makedirs(Path(str(TRANSFERRED_DIR)), exist_ok=True)
                transferred_path = os.path.join(
                    str(TRANSFERRED_DIR), os.path.basename(file_path)
                )
                shutil.move(file_path, transferred_path)
                if DEBUG:
                    logger.info(f"Moved {file_path} to {transferred_path}")
            except Exception as e:
                if DEBUG:
                    logger.error(f"Error processing {file_path}: {str(e)}")
