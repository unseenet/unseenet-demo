#!/usr/bin/env python3
"""Make the Unseenet demo, with the `unseenet` command line and nothing else.

    demo.py up        make what is missing: identities, groups, profiles, feeds, posts,
                      pins, chat and the site (safe to run again)
    demo.py reset     withdraw everything in the demo's groups and feeds - also what
                      others wrote - and make the demo again (the weekly reset)
    demo.py down [--remove-groups]
                      withdraw everything; --remove-groups also removes the groups for
                      good (their names cannot be used again)

Settings are in demo.toml (or the file in DEMO_CONFIG). The secret is the demo seed:
64 hex characters in UNSEENET_DEMO_SEED, or in the file demo.toml names. Every
fictional person's key is derived from it and their name, so the same seed always
gives the same people. What has been made is remembered in the state file.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"


class Demo:
    def __init__(self, config_path: Path):
        self.cfg = tomllib.loads(config_path.read_text())
        self.prefix = self.cfg["prefix"]
        self.vault = str((config_path.parent / self.cfg.get("vault", "demo.vault")).resolve())
        self.state_path = (config_path.parent / self.cfg.get("state", "state.json")).resolve()
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        for k in ("posted", "pages", "profiles", "pins"):
            self.state.setdefault(k, {})
        self.people = tomllib.loads((CONTENT / "people.toml").read_text())
        self.groups = tomllib.loads((CONTENT / "groups.toml").read_text())
        self.credits = json.loads((CONTENT / "pictures" / "credits.json").read_text())
        self.unseenet = self.cfg.get("unseenet", "unseenet")
        self.env = {**os.environ, "UNSEENET_PASSPHRASE": os.environ.get(
            "UNSEENET_DEMO_PASSPHRASE", self.cfg.get("passphrase", "demo"))}

    # --- the command line ---
    def run(self, *args, who: str | None = None, stdin: str | None = None) -> dict:
        cmd = [self.unseenet, "--json", "--vault", self.vault]
        if who:
            cmd += ["--identity", who]
        cmd += [str(a) for a in args]
        print("  $ unseenet", " ".join(cmd[4:])[:150], flush=True)
        r = subprocess.run(cmd, input=stdin, text=True, capture_output=True, env=self.env)
        if r.returncode != 0:
            raise SystemExit(f"unseenet {' '.join(cmd[4:])}\n{r.stderr.strip() or r.stdout.strip()}")
        lines = [ln for ln in r.stdout.strip().splitlines() if ln.startswith("{")]
        return json.loads(lines[-1]) if lines else {}

    def save(self) -> None:
        self.state_path.write_text(json.dumps(self.state, indent=2, ensure_ascii=False) + "\n")

    # --- names ---
    def seed(self) -> bytes:
        text = os.environ.get("UNSEENET_DEMO_SEED") or ""
        if not text and self.cfg.get("seed_file"):
            text = Path(self.cfg["seed_file"]).expanduser().read_text()
        seed = bytes.fromhex(text.strip())
        if len(seed) != 32:
            raise SystemExit("the demo seed is 64 hex characters (UNSEENET_DEMO_SEED or seed_file)")
        return seed

    def person_seed(self, name: str) -> str:
        return hmac.new(self.seed(), b"unseenet-demo/" + name.encode(), hashlib.sha256).hexdigest()

    def group_id(self, key: str) -> str:
        if key.startswith("feed:"):
            return f"feed@{self.state['people'][key[5:]]['fingerprint']}"
        name = self.groups[key]["name"]
        full = self.prefix + (f".{name}" if name else "")
        return f"{full}@{self.state['people']['demo']['fingerprint']}"

    def picture(self, name: str) -> Path:
        return next((CONTENT / "pictures").glob(f"{name}.*"))

    def source_line(self, name: str) -> str:
        c = self.credits[name]
        return (f"Photo: {c['author']}, {c['license']}, via Wikimedia Commons "
                f"({c['page']})")

    # --- making it ---
    def identities(self) -> None:
        print("Identities")
        people = self.state.setdefault("people", {})
        for name, p in self.people.items():
            r = self.run("id-import", name, "--display", p["display"], stdin=self.person_seed(name) + "\n")
            people[name] = {"fingerprint": r["fingerprint"], "key": r["key"]}
        for node in self.cfg.get("nodes", []):
            subprocess.run([self.unseenet, "--vault", self.vault, "node-add", node], env=self.env,
                           capture_output=True, check=True)
        self.save()

    def make_groups(self) -> None:
        print("Groups")
        made = self.state.setdefault("groups", {})
        for key, g in self.groups.items():
            gid = self.group_id(key)
            if made.get(key) == gid:
                continue
            args = ["group-create", gid.rsplit("@", 1)[0], "--type", g["type"],
                    "--title", g.get("title", ""), "--description", g.get("description", "")]
            for opt in ("view", "comments", "kinds", "max_pins", "max_pages", "home", "attachments", "types"):
                if opt in g:
                    args += [f"--{opt.replace('_', '-')}", g[opt]]
            if g.get("rules"):
                args += ["--rules", CONTENT / g["rules"]]
            for poster in g.get("posters", []):
                args += ["--poster", self.state["people"][poster]["key"]]
            r = self.run(*args, who="demo")
            assert r["group"] == gid, (r, gid)
            made[key] = gid
            self.save()

    def profiles(self) -> None:
        print("Profiles and feeds")
        for name, p in self.people.items():
            digest = hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()[:16]
            if self.state["profiles"].get(name) == digest:
                continue
            args = ["profile", "--about", p.get("about", ""), "--yes"]
            for link in p.get("links", []):
                args += ["--link", link]
            for lang in p.get("lang", []):
                args += ["--lang", lang]
            if p.get("picture"):
                args += ["--picture", self.picture(p["picture"]), "--alt", p["display"]]
            self.run(*args, who=name)
            if name != "demo":
                self.run("feed-start", "--yes", who=name)
            self.state["profiles"][name] = digest
            self.save()

    def posts(self) -> None:
        print("Posts")
        posted = self.state["posted"]
        for post in tomllib.loads((CONTENT / "posts.toml").read_text())["post"]:
            if post["key"] in posted:
                continue
            body = post.get("body", "").strip() + "\n"
            args = ["post", self.group_id(post["group"])]
            if post.get("reply_to"):
                args += ["--reply-to", posted[post["reply_to"]]]
            if post.get("subject"):
                args += ["-s", post["subject"]]
            for pic in post.get("pictures", []):
                args += ["--attach", self.picture(pic)]
                body += "\n" + self.source_line(pic) + "\n"
            args += ["--body", body]
            r = self.run(*args, who=post["by"])
            posted[post["key"]] = r["message_id"]
            self.save()
            if post.get("pin"):
                self.run("pin", self.group_id(post["group"]), r["message_id"], "--note", post["pin"],
                         who="demo")
                self.state["pins"][post["key"]] = True
                self.save()

    def chat(self) -> None:
        print("Chat")
        posted = self.state["posted"]
        lines = tomllib.loads((CONTENT / "chat.toml").read_text())["lines"]
        for i, (who, text) in enumerate(lines):
            key = f"chat-{i}"
            if key not in posted:
                r = self.run("post", self.group_id("chat"), "--kind", "chat", "--body", text, who=who)
                posted[key] = r["message_id"]
                self.save()

    def fill(self, text: str) -> str:
        """The placeholders of the site's pages, as this demo's addresses."""
        def sub(m):
            kind, arg = m.group(1), m.group(2)
            if kind == "address":
                return f"unseenet:{self.group_id(arg)}"
            if kind == "feed":
                return f"unseenet:{self.group_id('feed:' + arg)}"
            if kind == "person":
                return f"unseenet:{self.state['people'][arg]['fingerprint']}"
            if kind == "picture":            # images on pages: unseenet#427
                return f"*({self.credits[arg]['description'][:80] or arg} - {self.source_line(arg)})*"
            return m.group(0)
        return re.sub(r"\{(address|feed|person|picture):([a-z]+)\}", sub, text)

    def site(self) -> None:
        print("Site")
        gid = self.group_id("site")
        pages = {}
        for f in sorted((CONTENT / "site").glob("*.md")):
            head, _, text = f.read_text().partition("+++\n")[2].partition("+++\n")
            pages[f.stem] = (tomllib.loads(head)["title"], self.fill(text))
        rows = "\n".join(f"| {n} | {c['author']} | {c['license']} | [{c['title'].removeprefix('File:')}]"
                         f"({c['page']}) |" for n, c in self.credits.items())
        pages["credits"] = ("Credits", "# Credits\n\nThe pictures come from Wikimedia Commons and "
                            "keep their own licences: public domain, CC0 or CC BY.\n\n"
                            "| Picture | By | Licence | Source |\n|---|---|---|---|\n" + rows
                            + "\n\n[Back to the start](index)\n")
        for path, (title, text) in pages.items():
            digest = hashlib.sha256((title + text).encode()).hexdigest()[:16]
            if self.state["pages"].get(path) == digest:
                continue
            tmp = self.state_path.parent / f".page-{path}.md"
            tmp.write_text(text)
            self.run("page-put", gid, path, tmp, "--title", title, who="demo")
            tmp.unlink()
            self.state["pages"][path] = digest
            self.save()

    def up(self) -> None:
        self.identities()
        self.make_groups()
        self.profiles()
        self.posts()
        self.chat()
        self.site()
        print("Done:", ", ".join(self.group_id(k) for k in self.groups))

    # --- taking it down ---
    def withdraw_all(self) -> None:
        print("Withdrawing everything")
        for key in self.state.get("groups", {}):
            self.run("withdraw", self.group_id(key), "--all", "--yes", who="demo")
        for name in self.people:
            if name != "demo":
                self.run("withdraw", self.group_id(f"feed:{name}"), "--all", "--yes", who=name)
        self.state["posted"], self.state["pages"], self.state["pins"] = {}, {}, {}
        self.save()

    def reset(self) -> None:
        self.identities()
        self.withdraw_all()
        self.up()

    def down(self, remove_groups: bool) -> None:
        self.identities()
        self.withdraw_all()
        if remove_groups:
            for key in list(self.state.get("groups", {})):
                self.run("group-remove", self.group_id(key), "--reason", "the demo is taken down",
                         "--yes", who="demo")
            for name in self.people:
                if name != "demo":
                    self.run("group-remove", self.group_id(f"feed:{name}"), "--yes", who=name)
            self.state["groups"], self.state["profiles"] = {}, {}
            self.save()


def main(argv: list[str]) -> None:
    if not argv or argv[0] not in ("up", "reset", "down"):
        raise SystemExit(__doc__)
    demo = Demo(Path(os.environ.get("DEMO_CONFIG", ROOT / "demo.toml")))
    if argv[0] == "up":
        demo.up()
    elif argv[0] == "reset":
        demo.reset()
    else:
        demo.down("--remove-groups" in argv)


if __name__ == "__main__":
    main(sys.argv[1:])
