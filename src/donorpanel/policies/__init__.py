from pathlib import Path
from typing import Any

import yaml

POLICY_DIR = Path(__file__).parent


def load(policy_id: str) -> dict[str, Any]:
    path = POLICY_DIR / f"{policy_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no policy named {policy_id} in {POLICY_DIR}")
    return yaml.safe_load(path.read_text())


def available() -> list[str]:
    return sorted(p.stem for p in POLICY_DIR.glob("*.yaml"))
