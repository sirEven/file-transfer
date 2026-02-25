from pathlib import Path
from typing import List

import shutil
import os
import subprocess

import time
from dotenv import load_dotenv

from file_transfer.file_transfer import FileTransfer

# TODO: Rewrite this script "in maintainable" 🦾🤖...
# TODO: Implement recursive folder handling (if not yet covered by watchdog)
# TODO: Make bigger files work as well - e.g.: Podcasts.


class RemoteFileTransfer(FileTransfer):
    def setup(self) -> None:
        load_dotenv()
        self._dest_host = os.getenv("DEST_HOST")
        self._dest_user = os.getenv("DEST_USER")

    def transfer_file(self, file_path: Path):
        with self.transfer_lock:  # Ensure exclusive execution
            try:
                if file_path in self._processed_files:
                    if self._debug:
                        self._logger.info(
                            f"File already processed, skipping: {file_path}"
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
                        f"{self._dest_user}@{self._dest_host}:{self._dest_dir}",
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
                                returncode,
                                scp_command,
                                stderr_output,
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
