from pathlib import Path
from typing import Any, Dict
import json


def load_config(config_path: Path) -> Dict[str, Any]:
    with open(config_path, "r") as f:
        return json.load(f)
