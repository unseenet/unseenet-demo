#!/usr/bin/env python3
"""Ripen the demo's keys on this machine, in the background - stop and start as you like.

    python tools/ripen.py start [--to 2]   start (or go on) ripening every demo key
    python tools/ripen.py status           how far each key is, and whether it runs
    python tools/ripen.py stop             stop; the key files are deleted, the progress kept
    python tools/ripen.py clean            stop, and forget the progress too

Each key ripens in its own process at the lowest priority (nice 19), so the machine
stays quick for other things. A stop loses at most the segment being computed; the
chain so far is kept in the state files, which hold no secret. The keys are derived
from the demo seed only while ripening runs, into a folder only you can read, and
deleted when a key is done or stopped. When a key reaches the level, its chain is
published to the node, where the weekly run picks it up.

Settings: the seed (UNSEENET_DEMO_SEED, or --seed FILE, default
~/Unseenet/backup/unseenet-demo.seed), the node to publish to (--node), and the
unseenet command (--unseenet).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import signal
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = Path.home() / ".local" / "share" / "unseenet-demo-ripening"
NODE = "f6vnchi5p7ll4yn6yot6cz4ohzuxy3uhc3kztafuwn3zlyoup6tn64qd.onion"
UNSEENET = Path.home() / "Unseenet" / "unseenet" / ".venv" / "bin" / "unseenet"
SEED = Path.home() / "Unseenet" / "backup" / "unseenet-demo.seed"
LEVELS = (1 << 26, 1 << 29, 1 << 32, 1 << 35, 1 << 37)      # UN-RFC 0025 section 4


def people() -> list[str]:
    return list(tomllib.loads((ROOT / "content" / "people.toml").read_text()))


def seed(path: Path) -> bytes:
    text = os.environ.get("UNSEENET_DEMO_SEED") or path.expanduser().read_text()
    s = bytes.fromhex(text.strip())
    if len(s) != 32:
        raise SystemExit("the demo seed is 64 hex characters")
    return s


def paths(name: str) -> dict[str, Path]:
    return {"key": WORK / "keys" / f"{name}.key", "state": WORK / f"{name}.state.json",
            "log": WORK / f"{name}.log", "pid": WORK / f"{name}.pid"}


def running(name: str) -> int | None:
    p = paths(name)["pid"]
    try:
        pid = int(p.read_text())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def level(name: str) -> tuple[int | None, int]:
    try:
        data = json.loads(paths(name)["state"].read_text())["data"]
        segs = next(iter(data["ripening"].values()))["segments"]
        t = sum(int(s["t"]) for s in segs)
    except (OSError, KeyError, ValueError, StopIteration):
        return None, 0
    lv = None
    for i, th in enumerate(LEVELS):
        if t >= th:
            lv = i
    return lv, t


def start(args) -> None:
    secret = seed(Path(args.seed))
    (WORK / "keys").mkdir(parents=True, exist_ok=True)
    os.chmod(WORK, 0o700)
    os.chmod(WORK / "keys", 0o700)
    for name in people():
        if running(name):
            print(f"{name:6} already ripening")
            continue
        lv, _ = level(name)
        if lv is not None and lv >= args.to:
            print(f"{name:6} at level {lv} already")
            continue
        p = paths(name)
        p["key"].write_text(hmac.new(secret, b"unseenet-demo/" + name.encode(), hashlib.sha256).hexdigest() + "\n")
        os.chmod(p["key"], 0o600)
        # the key file goes when the process ends, however it ends
        cmd = (f"nice -n 19 '{args.unseenet}' ripen --key-file '{p['key']}' --state '{p['state']}' "
               f"--to {args.to} --publish --node '{args.node}'; rm -f '{p['key']}'")
        with open(p["log"], "a") as log:
            proc = subprocess.Popen(["sh", "-c", cmd], stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True)
        p["pid"].write_text(str(proc.pid))
        print(f"{name:6} started (level {lv if lv is not None else '-'} so far)")


def stop(args) -> None:
    for name in people():
        pid = running(name)
        if pid:
            os.killpg(pid, signal.SIGTERM)
            print(f"{name:6} stopped")
        paths(name)["pid"].unlink(missing_ok=True)
        paths(name)["key"].unlink(missing_ok=True)


def status(args) -> None:
    for name in people():
        lv, t = level(name)
        state = "ripening" if running(name) else "stopped"
        last = ""
        log = paths(name)["log"]
        if log.exists():
            lines = [ln.strip() for ln in log.read_text().splitlines() if ln.strip()]
            last = lines[-1][:90] if lines else ""
        print(f"{name:6} {state:9} level {'-' if lv is None else lv}, t = {t:,}   {last}")
    keys = list((WORK / "keys").glob("*.key")) if (WORK / "keys").exists() else []
    print(f"key files on disk: {len(keys)}" + ("" if any(running(n) for n in people()) or not keys
                                                else " - none should be: run stop"))


def clean(args) -> None:
    stop(args)
    for name in people():
        for k in ("state", "log"):
            paths(name)[k].unlink(missing_ok=True)
    print("progress forgotten")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["start", "stop", "status", "clean"])
    ap.add_argument("--to", type=int, default=2, help="the level to ripen to (default 2)")
    ap.add_argument("--seed", default=str(SEED))
    ap.add_argument("--node", default=NODE)
    ap.add_argument("--unseenet", default=str(UNSEENET))
    args = ap.parse_args()
    {"start": start, "stop": stop, "status": status, "clean": clean}[args.command](args)


if __name__ == "__main__":
    main()
