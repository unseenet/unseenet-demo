#!/usr/bin/env python3
"""Make and keep the Unseenet demo, with the `unseenet` command line.

    demo.py weekly    the weekly run: withdraw what visitors wrote, make what is
                      missing, and post this week's news - from the pool, from the
                      almanac, and (with a key) written by a language model
    demo.py up        only make what is missing: people, groups, the base posts, the site
    demo.py down [--remove-groups]
                      withdraw everything; --remove-groups removes the groups for good

**The network is the state.** What exists is read from the groups (`unseenet read
--json`), so every run can start from an empty machine: a post from the pool is
"used" while the person has a post with that subject there, and free again once it
has expired (90 days); a picture likewise, by its blob ID. Nothing is posted twice
while the earlier one is still there.

Settings are in demo.toml (or DEMO_CONFIG). Secrets: the demo seed (UNSEENET_DEMO_SEED,
or the file seed_file names), and for the language model its key (llm.key_env).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import re
import subprocess
import sys
import tomllib
import urllib.request
from datetime import date
from pathlib import Path

import almanac

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
PER_WEEK = 1                     # pool posts per person per week


class Demo:
    def __init__(self, config_path: Path):
        self.cfg = tomllib.loads(config_path.read_text())
        self.prefix = self.cfg["prefix"]
        self.vault = str((config_path.parent / self.cfg.get("vault", "demo.vault")).resolve())
        self.unseenet = self.cfg.get("unseenet", "unseenet")
        self.people = tomllib.loads((CONTENT / "people.toml").read_text())
        self.groups = tomllib.loads((CONTENT / "groups.toml").read_text())
        self.credits = json.loads((CONTENT / "pictures" / "credits.json").read_text())
        self.env = {**os.environ, "UNSEENET_PASSPHRASE": os.environ.get(
            "UNSEENET_DEMO_PASSPHRASE", self.cfg.get("passphrase", "demo"))}
        self.today = date.fromisoformat(os.environ["DEMO_DATE"]) if os.environ.get("DEMO_DATE") else date.today()
        self.keys: dict[str, dict] = {}
        self._read: dict[str, list] = {}
        self._blob_ids: dict[str, str] = {}

    # --- the command line ---
    def run(self, *args, who: str | None = None, stdin: str | None = None, check: bool = True) -> dict:
        cmd = [self.unseenet, "--json", "--vault", self.vault]
        if who:
            cmd += ["--identity", who]
        cmd += [str(a) for a in args]
        print("  $ unseenet", " ".join(cmd[4:])[:150], flush=True)
        r = subprocess.run(cmd, input=stdin, text=True, capture_output=True, env=self.env)
        if r.returncode != 0:
            if not check:
                return {"error": (r.stderr or r.stdout).strip()}
            raise SystemExit(f"unseenet {' '.join(cmd[4:])}\n{r.stderr.strip() or r.stdout.strip()}")
        lines = [ln for ln in r.stdout.strip().splitlines() if ln.startswith("{")]
        return json.loads(lines[-1]) if lines else {}

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
            return f"feed@{self.keys[key[5:]]['fingerprint']}"
        name = self.groups[key]["name"]
        return f"{self.prefix}{'.' + name if name else ''}@{self.keys['demo']['fingerprint']}"

    def picture(self, name: str) -> Path:
        return next((CONTENT / "pictures").glob(f"{name}.*"))

    def source_line(self, name: str) -> str:
        c = self.credits[name]
        return f"Photo: {c['author']}, {c['license']}, via Wikimedia Commons ({c['page']})"

    def blob_id(self, name: str) -> str:
        """The blob ID a picture gets once cleaned - the same every time, so it shows
        whether a picture is in use (computed with the unseenet library, nothing sent)."""
        if name not in self._blob_ids:
            from unseenet.client.media import prepare
            from unseenet.core.blobs import blob_id
            p = self.picture(name)
            self._blob_ids[name] = blob_id(prepare(p.name, p.read_bytes()).octets)
        return self._blob_ids[name]

    # --- what is there ---
    def posts_in(self, gid: str, refresh: bool = False) -> list:
        if refresh or gid not in self._read:
            r = self.run("read", gid, who="demo", check=False)
            self._read[gid] = r.get("posts", [])
        return self._read[gid]

    def exists(self, gid: str, who: str, subject: str | None = None, body: str | None = None) -> str | None:
        key = self.keys[who]["key"]
        for p in self.posts_in(gid):
            if p["author_key"] != key:
                continue
            if subject is not None and p["subject"] == subject:
                return p["message_id"]
            if body is not None and p["body"].strip().startswith(body.strip()[:80]):
                return p["message_id"]
        return None

    def pictures_in_use(self) -> set[str]:
        groups = [self.group_id(k) for k in self.groups] + \
                 [self.group_id(f"feed:{n}") for n in self.people if n != "demo"]
        return {b for g in groups for p in self.posts_in(g) for b in p["blobs"]}

    def pick_picture(self, theme: str, in_use: set[str]) -> str | None:
        """A picture with this theme that no post uses now (or the name itself)."""
        if theme in self.credits:
            return theme
        free = [n for n, c in self.credits.items() if theme in c.get("themes", [])
                and self.blob_id(n) not in in_use]
        if not free:
            return None
        choice = random.Random(f"{self.today}-{theme}").choice(free)
        in_use.add(self.blob_id(choice))
        return choice

    # --- making things ---
    def identities(self) -> None:
        print("Identities")
        for name, p in self.people.items():
            self.keys[name] = self.run("id-import", name, "--display", p["display"],
                                       stdin=self.person_seed(name) + "\n")
        for node in self.cfg.get("nodes", []):
            subprocess.run([self.unseenet, "--vault", self.vault, "node-add", node], env=self.env,
                           capture_output=True)

    def make_groups(self) -> None:
        print("Groups")
        for key, g in self.groups.items():
            gid = self.group_id(key)
            have = self.run("group-show", gid, who="demo", check=False)
            if "error" not in have:
                self.sync_settings(gid, g, have)
                continue
            args = ["group-create", gid.rsplit("@", 1)[0], "--type", g["type"],
                    "--title", g.get("title", ""), "--description", g.get("description", "")]
            for opt in ("view", "comments", "kinds", "max_pins", "max_pages", "home", "attachments",
                        "types", "retention_days"):
                if opt in g:
                    args += [f"--{opt.replace('_', '-')}", g[opt]]
            if g.get("rules"):
                args += ["--rules", CONTENT / g["rules"]]
            for poster in g.get("posters", []):
                args += ["--poster", self.keys[poster]["key"]]
            self.run(*args, who="demo")

    def sync_settings(self, gid: str, g: dict, have: dict) -> None:
        """A group made before groups.toml changed: its files and retention as now."""
        args = []
        if "attachments" in g:
            want = {"max_size": g["attachments"]} | ({"types": g["types"].split(",")} if g.get("types") else {})
            if have.get("attachments") != want:
                args += ["--attachments", g["attachments"]] + (["--types", g["types"]] if g.get("types") else [])
        if have.get("retention_days", 90) != g.get("retention_days", 90):
            args += ["--retention-days", g.get("retention_days", 90)]
        if args:
            self.run("group-edit", gid, *args, who="demo")

    def profiles(self) -> None:
        print("Profiles and personal feeds")
        llm = bool(self.llm_config())
        for name, p in self.people.items():
            mine = self.run("profile", "--of", self.keys[name]["fingerprint"], who=name).get("profile") or {}
            about = p.get("about", "") + ("\n\nSome posts here are written with a language model."
                                          if llm and name != "demo" else "")
            if mine.get("about") != about:
                args = ["profile", "--about", about, "--yes"]
                for link in p.get("links", []):
                    args += ["--link", link]
                for lang in p.get("lang", []):
                    args += ["--lang", lang]
                if p.get("picture"):
                    args += ["--picture", self.picture(p["picture"]), "--alt", p["display"]]
                self.run(*args, who=name)
            if name != "demo":
                self.run("feed-start", "--attachments", 1048576, "--types", "image/*", "--yes", who=name)

    def post(self, item: dict, in_use: set[str], parent: str | None = None) -> str | None:
        """One post (or comment) unless the person has it there already."""
        who, gid = item["by"], self.group_id(item["group"])
        subject, body = item.get("subject"), item.get("body", "").strip() + "\n"
        found = self.exists(gid, who, subject=subject) if subject else self.exists(gid, who, body=body)
        if found:
            return found
        args = ["post", gid]
        if parent:
            args += ["--reply-to", parent]
        if subject:
            args += ["-s", subject]
        for want in item.get("pictures", []):
            name = self.pick_picture(want, in_use)
            if name:
                args += ["--attach", self.picture(name)]
                body += "\n" + self.source_line(name) + "\n"
        if item.get("kind") == "chat":
            args += ["--kind", "chat"]
        r = self.run(*args, "--body", body, who=who, check=False)
        if "error" in r:
            print(f"    not posted: {r['error'][-200:]}")
            return None
        self.posts_in(gid).append({"message_id": r["message_id"], "author_key": self.keys[who]["key"],
                                   "subject": subject or "", "body": body, "blobs": []})
        return r["message_id"]

    def base(self) -> None:
        """The demo's base posts (welcome, pinned) - posted again when expired."""
        print("Base posts")
        in_use = self.pictures_in_use()
        ids = {}
        for item in tomllib.loads((CONTENT / "posts.toml").read_text())["post"]:
            parent = ids.get(item.get("reply_to")) if item.get("reply_to") else None
            if item.get("reply_to") and not parent:
                continue
            mid = self.post(item, in_use, parent)
            if mid:
                ids[item["key"]] = mid
            if mid and item.get("pin"):
                gid = self.group_id(item["group"])
                pinned = {p["id"] for p in self.run("pins", gid, who="demo").get("pins", [])}
                if mid not in pinned:
                    self.run("pin", gid, mid, "--note", item["pin"], who="demo")

    def pool(self) -> None:
        """This week's posts from the pool: for each person, posts of this season (or
        any) that are not there now, chosen by the week, with their comments."""
        print("This week from the pool")
        season = almanac.season(self.today)
        in_use = self.pictures_in_use()
        rng = random.Random(str(self.today.isocalendar()[:2]))
        for name in (n for n in self.people if n != "demo"):
            path = CONTENT / "pool" / f"{name}.toml"
            if not path.exists():
                continue
            items = tomllib.loads(path.read_text()).get("post", [])
            free = [i for i in items if i.get("season", "any") in (season, "any")
                    and not self.exists(self.group_id(i.get("group", f"feed:{name}")), name, subject=i["subject"])]
            rng.shuffle(free)
            for item in free[:PER_WEEK]:
                item = {"group": f"feed:{name}", **item, "by": name}
                mid = self.post(item, in_use)
                for c in item.get("comments", []) if mid else []:
                    self.post({"group": item["group"], "by": c["by"], "body": c["body"]}, in_use, mid)

    def almanac_posts(self) -> None:
        print("The almanac")
        for name, make in almanac.FOR.items():
            subject, body = make(self.today)
            self.post({"by": name, "group": f"feed:{name}", "subject": subject, "body": body}, set())

    def chat(self) -> None:
        """A bit of chat: this week's conversation from the pool, if not there now."""
        print("Chat")
        chats = tomllib.loads((CONTENT / "chat.toml").read_text())
        talks = chats.get("talk", []) or [{"lines": chats.get("lines", [])}]
        gid = self.group_id("chat")
        free = [t for t in talks if not any(self.exists(gid, w, body=line) for w, line in t["lines"][:1])]
        if free:
            talk = random.Random(str(self.today.isocalendar()[:2])).choice(free)
            for who, line in talk["lines"]:
                self.post({"by": who, "group": "chat", "body": line, "kind": "chat"}, set())

    # --- the language model (optional) ---
    def llm_config(self) -> dict | None:
        llm = self.cfg.get("llm")
        if not llm:
            return None
        key = os.environ.get(llm.get("key_env", ""), "") if llm.get("key_env") else ""
        if llm.get("key_env") and not key:
            return None
        return {**llm, "key": key}

    def ask(self, llm: dict, prompt: str) -> dict | None:
        """One chat completion (OpenAI-compatible: OpenRouter, Ollama); the first model
        that answers. Tried once each - free models fail often, and fails count."""
        for model in llm.get("models", []):
            body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                               "temperature": 0.9, "max_tokens": 400}).encode()
            req = urllib.request.Request(llm["url"].rstrip("/") + "/chat/completions", data=body,
                                         headers={"Content-Type": "application/json",
                                                  **({"Authorization": f"Bearer {llm['key']}"} if llm["key"] else {})})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    text = json.load(r)["choices"][0]["message"]["content"]
            except Exception as exc:  # noqa: BLE001 - any failure: try the next model
                print(f"    {model}: {str(exc)[:100]}")
                continue
            m = re.search(r"\{.*\}", text, re.S)
            try:
                out = json.loads(m.group(0)) if m else None
            except json.JSONDecodeError:
                out = None
            if out and isinstance(out.get("subject"), str) and isinstance(out.get("body"), str) \
                    and 3 <= len(out["subject"]) <= 80 and 20 <= len(out["body"]) <= 1200:
                return out
            print(f"    {model}: no usable answer")
        return None

    def llm_posts(self) -> None:
        llm = self.llm_config()
        if not llm:
            return
        print("Written by a language model")
        season = almanac.season(self.today)
        for name in llm.get("people", [n for n in self.people if n != "demo"]):
            p = self.people[name]
            recent = [x["subject"] for x in self.posts_in(self.group_id(f"feed:{name}")) if x["subject"]][-8:]
            prompt = (f"You write one short post for {p['display']}, a fictional person in a small, "
                      f"friendly online village. About them: {p['about']} It is {season}, "
                      f"{self.today:%d %B}. Recent posts, do not repeat them: {recent}. "
                      "Write in English, warm and concrete, 2-4 sentences, no hashtags, nothing "
                      "about real people, no advice that could hurt. Answer only with JSON: "
                      '{"subject": "...", "body": "..."}')
            out = self.ask(llm, prompt)
            if out:
                self.post({"by": name, "group": f"feed:{name}", "subject": out["subject"].strip(),
                           "body": out["body"].strip()}, set())

    # --- the site ---
    def fill(self, text: str) -> str:
        def sub(m):
            kind, arg = m.group(1), m.group(2)
            if kind == "address":
                return f"unseenet:{self.group_id(arg)}"
            if kind == "feed":
                return f"unseenet:{self.group_id('feed:' + arg)}"
            if kind == "person":
                return f"unseenet:{self.keys[arg]['fingerprint']}"
            if kind == "picture":
                alt = (self.credits[arg]["description"] or arg)[:100].replace("]", ")")
                return f"![{alt}](file:{self.picture(arg)})\n\n*{self.source_line(arg)}*"
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
        now = {p["page"]: p for p in self.posts_in(gid) if p.get("page")}
        for path, (title, text) in pages.items():
            expected = re.sub(r"\(file:([^)]+)\)",
                              lambda m: f"({self.blob_id(Path(m.group(1)).stem)})", text).strip()
            cur = now.get(path)
            if cur and cur["subject"] == title and cur["body"].strip() == expected:
                continue
            tmp = ROOT / f".page-{path}.md"
            tmp.write_text(text)
            self.run("page-put", gid, path, tmp, "--title", title, who="demo")
            tmp.unlink()

    # --- the runs ---
    def withdraw_visitors(self) -> None:
        print("Withdrawing what visitors wrote")
        ours = [a for n in self.people for a in ("--keep-author", self.keys[n]["key"])]
        for key in self.groups:
            if key != "site":
                self.run("withdraw", self.group_id(key), "--all", *ours, "--yes", who="demo", check=False)
        for name in self.people:
            if name != "demo":
                self.run("withdraw", self.group_id(f"feed:{name}"), "--all", *ours, "--yes",
                         who=name, check=False)
        self._read.clear()

    def up(self) -> None:
        self.identities()
        self.make_groups()
        self.profiles()
        self.base()
        self.chat()
        self.site()

    def weekly(self) -> None:
        self.identities()
        self.make_groups()
        self.withdraw_visitors()
        self.profiles()
        self.base()
        self.pool()
        self.almanac_posts()
        self.llm_posts()
        self.chat()
        self.site()
        print("Done for", almanac.week(self.today))

    def down(self, remove_groups: bool) -> None:
        self.identities()
        for key in self.groups:
            self.run("withdraw", self.group_id(key), "--all", "--yes", who="demo", check=False)
        for name in self.people:
            if name != "demo":
                self.run("withdraw", self.group_id(f"feed:{name}"), "--all", "--yes", who=name, check=False)
        if remove_groups:
            for key in self.groups:
                self.run("group-remove", self.group_id(key), "--reason", "the demo is taken down",
                         "--yes", who="demo", check=False)
            for name in self.people:
                if name != "demo":
                    self.run("group-remove", self.group_id(f"feed:{name}"), "--yes", who=name, check=False)


def main(argv: list[str]) -> None:
    if not argv or argv[0] not in ("up", "weekly", "down"):
        raise SystemExit(__doc__)
    demo = Demo(Path(os.environ.get("DEMO_CONFIG", ROOT / "demo.toml")))
    {"up": demo.up, "weekly": demo.weekly}.get(argv[0], lambda: demo.down("--remove-groups" in argv))()


if __name__ == "__main__":
    main(sys.argv[1:])
