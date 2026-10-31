"""Offline stand-in for ``hf download`` and ``mlx_lm.convert``.

Implements: US-2.4 test harness (ES-4: no network). It writes a model the way the real tools would
(``config.json`` plus a safetensors file) and appends one JSON line per call to ``$FAKE_HF_LOG``
with its argv and whether ``HF_HUB_OFFLINE`` was set. Knobs: ``FAKE_HF_EXIT`` (exit code),
``FAKE_HF_EMPTY=1`` (exit 0 without writing weights), ``FAKE_HF_SLEEP`` (seconds before writing).

Usage::

    python -m tests.fakes.fake_hf download REPO_ID --local-dir DIR
    python -m tests.fakes.fake_hf convert --hf-path SRC --mlx-path DST -q --q-bits N
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path

__all__ = ["main"]


def _write_model(target: Path, **config: object) -> None:
    target.mkdir(parents=True, exist_ok=True)
    (target / "config.json").write_text(json.dumps(config))
    (target / "model.safetensors").write_bytes(b"fake weights")


def main(argv: Sequence[str] | None = None) -> int:
    """Pretend to download or convert a model."""
    args_list = list(sys.argv[1:] if argv is None else argv)
    log = os.environ.get("FAKE_HF_LOG")
    if log:
        with Path(log).open("a", encoding="utf-8") as handle:
            offline = os.environ.get("HF_HUB_OFFLINE") == "1"
            handle.write(json.dumps({"argv": args_list, "offline": offline}) + "\n")
    time.sleep(float(os.environ.get("FAKE_HF_SLEEP", "0")))
    code = int(os.environ.get("FAKE_HF_EXIT", "0"))
    if code or os.environ.get("FAKE_HF_EMPTY") == "1":
        return code
    parser = argparse.ArgumentParser(prog="fake_hf")
    sub = parser.add_subparsers(dest="command", required=True)
    download = sub.add_parser("download")
    download.add_argument("repo_id")
    download.add_argument("--local-dir", type=Path, required=True)
    convert = sub.add_parser("convert")
    convert.add_argument("--hf-path", type=Path, required=True)
    convert.add_argument("--mlx-path", type=Path, required=True)
    convert.add_argument("-q", action="store_true")
    convert.add_argument("--q-bits", type=int, default=4)
    args = parser.parse_args(args_list)
    if args.command == "download":
        _write_model(args.local_dir, repo_id=args.repo_id)
    else:
        if not (args.hf_path / "config.json").is_file():
            return 2
        _write_model(args.mlx_path, quantization={"bits": args.q_bits})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
