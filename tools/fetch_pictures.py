"""Find free pictures for the demo on Wikimedia Commons and write CREDITS.md.

Only public domain, CC0 and CC BY (no ShareAlike, which would bind the demo's own
content to that licence). For each wanted picture: search Commons, take the first file
with a licence we accept and a size worth showing, download a 1024 px version, and
record what it is, who made it, the licence and where it came from.

    python tools/fetch_pictures.py        # writes content/pictures/ and CREDITS.md
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "content" / "pictures"
API = "https://commons.wikimedia.org/w/api.php"
UA = "unseenet-demo/0.1 (https://github.com/unseenet/unseenet-demo)"

# name -> search words (the first good match is taken)
WANTED = {
    "bees": "honey bees honeycomb",
    "hive": "beehive apiary",
    "antenna": "yagi antenna amateur radio mast",
    "radio": "amateur radio transceiver",
    "bread": "sourdough bread loaf crust",
    "bakery": "bread oven bakery",
    "trail": "mountain hiking trail",
    "lake": "mountain lake landscape",
    "guineapig": "guinea pig grass photo",
    "guineapigs": "two guinea pigs hay",
    "forest": "forest path autumn",
    "coast": "coast sea cliffs",
    "town": "old town street",
    "stars": "milky way over mountains night",
    "keyboard": "vintage computer keyboard",
    "tea": "cup of tea on table",
}


def accepted(licence: str) -> bool:
    """Public domain, CC0, or plain CC BY of any version - not ShareAlike (SA), which
    would bind the demo's content, nor NonCommercial (NC) or NoDerivatives (ND): the
    client changes every picture (metadata out, made smaller)."""
    lic = licence.strip().lower()
    if lic in ("pd", "cc0") or lic.startswith(("public domain", "cc0", "cc-zero")):
        return True
    words = set(re.split(r"[\s-]+", lic))
    return lic.startswith(("cc by", "cc-by")) and not words & {"sa", "nc", "nd"}


def get(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
        return json.load(r)


def clean(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def find(words: str):
    res = get({"action": "query", "generator": "search", "gsrsearch": f"filetype:bitmap {words}",
               "gsrnamespace": 6, "gsrlimit": 20, "prop": "imageinfo",
               "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 1024})
    pages = sorted(res.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    for p in pages:
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = clean(meta.get("LicenseShortName", {}).get("value", ""))
        if info.get("mime") not in ("image/jpeg", "image/png") or info.get("width", 0) < 800:
            continue
        if not accepted(lic) or re.search(r"\b(YPM|specimen|MET DT|painting|portrait of|museum)\b",
                                          p["title"], re.I):
            continue                        # not museum specimens or paintings
        if not 0.6 <= info.get("width", 1) / max(info.get("height", 1), 1) <= 2.0:
            continue                        # no panoramas or thin strips
        return {"title": p["title"], "page": info.get("descriptionurl"), "url": info.get("thumburl"),
                "license": lic, "license_url": meta.get("LicenseUrl", {}).get("value", ""),
                "author": re.sub(r"^(Unknown author)+$", "Unknown author",
                                 clean(meta.get("Artist", {}).get("value", ""))) or "Unknown author",
                "description": clean(meta.get("ImageDescription", {}).get("value", ""))[:200]}
    return None


def main() -> None:
    """All pictures, or only those named on the command line (keeping the others)."""
    OUT.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])
    saved = OUT / "credits.json"
    credits = json.loads(saved.read_text()) if only and saved.exists() else {}
    for name, words in WANTED.items():
        if only and name not in only:
            continue
        found = find(words)
        if not found:
            print(f"{name}: nothing with a licence we accept", file=sys.stderr)
            continue
        ext = ".png" if found["url"].lower().endswith(".png") else ".jpg"
        req = urllib.request.Request(found["url"], headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            (OUT / f"{name}{ext}").write_bytes(r.read())
        credits[name] = {**found, "file": f"content/pictures/{name}{ext}"}
        print(f"{name}: {found['title']} ({found['license']}, {found['author'][:40]})")
        time.sleep(1)                       # be polite to Commons
    (OUT / "credits.json").write_text(json.dumps(credits, indent=2, ensure_ascii=False) + "\n")
    lines = ["# Credits", "", "The pictures in `content/pictures/` come from "
             "[Wikimedia Commons](https://commons.wikimedia.org/) and keep their own licences: "
             "public domain, CC0 or CC BY. They are posted in the demo with their source, "
             "after the client has taken out their metadata.", "",
             "| File | What | By | Licence | Source |", "|---|---|---|---|---|"]
    for name, c in credits.items():
        lic = f"[{c['license']}]({c['license_url']})" if c["license_url"] else c["license"]
        what = (c["description"] or c["title"].removeprefix("File:")).replace("|", "/")[:90]
        lines.append(f"| `{Path(c['file']).name}` | {what} | {c['author'].replace('|', '/')[:60]} "
                     f"| {lic} | [{c['title'].removeprefix('File:')}]({c['page']}) |")
    (ROOT / "CREDITS.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
