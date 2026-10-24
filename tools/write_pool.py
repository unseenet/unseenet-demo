#!/usr/bin/env python3
"""Let a language model write new posts for the pool - to be read by a person first.

    python tools/write_pool.py [--per-person 3] [--season autumn]

For each of the demo's people it asks for a few new posts for the coming season, in
their own voice and not on subjects the pool has already, checks each answer, and
adds the good ones to content/pool/<person>.toml, marked ``written = "llm"``. It
changes only files: in GitHub Actions the change becomes a pull request, which a
person reads, edits and merges before anything is posted (.github/workflows/write.yml).
Each post costs one request once, and is used again and again from the pool.

The model is the one in the config (DEMO_CONFIG, default ci.toml): ``[llm]`` with an
OpenAI-compatible ``url``, ``models`` tried in order, and the key in ``key_env``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
sys.path.insert(0, str(ROOT))
import almanac  # noqa: E402


def ask(llm: dict, key: str, prompt: str) -> str | None:
    """The first model's answer that has text; each tried once (fails count on free plans)."""
    for model in llm["models"]:
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                           "temperature": 0.9, "max_tokens": 2500}).encode()
        req = urllib.request.Request(llm["url"].rstrip("/") + "/chat/completions", data=body,
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {key}"} if key else {})})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                text = json.load(r)["choices"][0]["message"].get("content") or ""
        except Exception as exc:  # noqa: BLE001 - any failure: the next model
            print(f"  {model}: {str(exc)[:100]}")
            continue
        if text.strip():
            print(f"  {model}: answered")
            return text
        print(f"  {model}: an empty answer")
    return None


def good(post, name: str, display: str, themes: set[str], taken: set[str]) -> dict | None:
    """A post worth a person's reading: the right shape and length, in the first person,
    not on a subject the pool has, no hashtags or links."""
    if not isinstance(post, dict):
        return None
    subject, body = str(post.get("subject", "")).strip(), str(post.get("body", "")).strip()
    if not (3 <= len(subject) <= 70 and 60 <= len(body) <= 700) or subject.lower() in taken:
        return None
    first = body.split()[0].strip(",.").lower() if body.split() else ""
    if first in (name, display.split()[0].lower()) or re.search(r"#\w|https?://|\"\"\"|\\\\", body + subject):
        return None                                  # third person, hashtags, links, quoting
    picture = post.get("picture")
    out = {"subject": subject, "body": body}
    if isinstance(picture, str) and picture in themes:
        out["pictures"] = [picture]
    return out


def toml_post(p: dict, season: str) -> str:
    def s(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"')
    lines = ["", "[[post]]", f'subject = "{s(p["subject"])}"', f'season = "{season}"', 'written = "llm"']
    if p.get("pictures"):
        lines.append(f'pictures = ["{p["pictures"][0]}"]')
    lines.append(f'body = """{p["body"]}"""')
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--per-person", type=int, default=3)
    ap.add_argument("--season", help="default: the season a month from today")
    args = ap.parse_args()
    cfg = tomllib.loads((ROOT / os.environ.get("DEMO_CONFIG", "ci.toml")).read_text())
    llm = cfg.get("llm")
    key = os.environ.get(llm.get("key_env", ""), "") if llm else ""
    if not llm or (llm.get("key_env") and not key):
        raise SystemExit("no language model configured (an [llm] section and its key)")
    season = args.season or almanac.season(date.today() + timedelta(days=30))
    people = tomllib.loads((CONTENT / "people.toml").read_text())
    credits = json.loads((CONTENT / "pictures" / "credits.json").read_text())
    themes = {t for c in credits.values() for t in c.get("themes", [])}
    written = 0
    for name, p in people.items():
        if name == "demo":
            continue
        path = CONTENT / "pool" / f"{name}.toml"
        pool = tomllib.loads(path.read_text()).get("post", []) if path.exists() else []
        taken = {i["subject"].lower() for i in pool}
        prompt = (
            f"You are {p['display']}, a made-up person in a small, friendly online village. "
            f"About you: {p['about']}\n\n"
            f"Write {args.per_person} short posts for your own feed for the {season}, each "
            "in the first person (\"I\"), warm and concrete, 2-4 sentences, about your own "
            "life and interests. Do not write about real people, places that can be found, "
            "politics, health advice or anything that could hurt. No hashtags, no links.\n"
            f"These subjects you have written about already - choose new ones: "
            f"{sorted(i['subject'] for i in pool)}\n"
            f"If a picture would suit a post, name one of these themes as \"picture\": "
            f"{sorted(themes)}; else leave it out.\n"
            'Answer with JSON only: [{"subject": "...", "body": "...", "picture": "..."}, ...]')
        print(f"{name}:")
        text = ask(llm, key, prompt)
        m = re.search(r"\[.*\]", text or "", re.S)
        try:
            posts = json.loads(m.group(0)) if m else []
        except json.JSONDecodeError:
            posts = []
        kept = []
        for post in posts if isinstance(posts, list) else []:
            g = good(post, name, p["display"], themes, taken)
            if g:
                kept.append(g)
                taken.add(g["subject"].lower())
        if kept:
            new = (path.read_text() if path.exists() else "") + "".join(toml_post(k, season) for k in kept)
            try:
                tomllib.loads(new)                        # checked before it is written
            except tomllib.TOMLDecodeError as exc:
                print(f"  not kept: the result would not be valid ({exc})")
                kept = []
            else:
                path.write_text(new)
        print(f"  kept {len(kept)} of {len(posts) if isinstance(posts, list) else 0}")
        written += len(kept)
    print(f"{written} new posts for the {season}")


if __name__ == "__main__":
    main()
