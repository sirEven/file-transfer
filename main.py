import sys
import time
import subprocess
import logging
from dotenv import load_dotenv
import os

from music_file_handler.music_file_handler import MusicFileHandler

# Load environment variables
load_dotenv()

# Configuration
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
LOG_FILE = os.getenv("LOG_FILE")

# Set up logging (file only, disabled in production)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO if DEBUG else logging.CRITICAL,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger()


def main():
    if DEBUG:
        try:
            import watchdog
        except ImportError:
            logger.info("Installing watchdog library")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "watchdog"], check=True
            )
            import watchdog
    else:
        import watchdog  # TODO: Clean up.

    # Create observer and event handler
    music_file_handler = MusicFileHandler()
    try:
        music_file_handler.start()  # Start the observer
        if DEBUG:
            logger.info("Main loop started")
        while True:
            time.sleep(1)  # Keep the daemon running
    except KeyboardInterrupt:
        print("Keyboard interrupt received. Exiting...")
        if DEBUG:
            logger.info("Received KeyboardInterrupt, stopping daemon")
        try:
            music_file_handler.stop()  # Stop the observer
        except Exception as e:
            if DEBUG:
                logger.error(f"Error stopping music_file_handler: {str(e)}")
        sys.exit(0)
    except Exception as e:
        if DEBUG:
            logger.error(f"Error in main loop: {str(e)}")
        music_file_handler.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
