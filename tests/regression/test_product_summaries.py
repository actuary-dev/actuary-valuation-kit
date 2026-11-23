"""Product-level CLI and preflight checks for a mixed book."""

import json
import subprocess
import sys

from avk.api import preflight
from avk.demo.generate import PRODUCTS, generate


def mixed_book(folder):
    config = None
    policies = {}
    for i, product in enumerate(PRODUCTS):
        path = generate(folder / product, product, 8 + i, 209)
        cfg = json.loads(path.read_text())
        config = cfg if config is None else config
        policies.update({k: v for k, v in cfg["Inputs"]["Replace"].items() if "polic" in k})
    config["Inputs"]["Replace"].update(policies)
    config["Products_to_run"] = list(PRODUCTS)
    config["Output_path"] = str(folder / "mixed-output")
    path = folder / "mixed.json"
    path.write_text(json.dumps(config))
    return path


def test_preflight_product_details(tmp_path):
    checks = preflight(mixed_book(tmp_path))
    assert all(c.ok for c in checks), checks
    messages = "\n".join(c.message for c in checks)
    for i, code in enumerate(PRODUCTS):
        assert f"{code}: {8 + i} policies;" in messages
        assert "372 months" in messages
        assert "tables;" in messages


def test_cli_product_details(tmp_path):
    path = mixed_book(tmp_path)
    for command in ("check", "run"):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from avk.cli import main; raise SystemExit(main())",
                command,
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        for i, code in enumerate(PRODUCTS):
            assert f"{code}: {8 + i} policies;" in result.stdout
