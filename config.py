from pathlib import Path
from typing import Any

import yaml



CONFIG_PATH = Path("config.yaml")



def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict):
        raise ValueError("Config must contain a YAML mapping")

    return config