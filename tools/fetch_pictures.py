"""Find free pictures for the demo on Wikimedia Commons, by theme, and write CREDITS.md.

Only public domain, CC0 and plain CC BY: no ShareAlike (it would bind the demo's own
content), no NonCommercial or NoDerivatives (the client changes every picture). For
each theme it searches Commons with a few queries and keeps files with a licence we
accept, a size worth showing and no sign of a painting, a museum object or a person's
portrait, until the theme has ``WANT`` pictures. Each becomes a JPEG of at most 1024 px
in content/pictures/, with its credits in credits.json and CREDITS.md.

Pictures already there are kept. A person still looks at every new one (a contact
sheet: --sheet); a picture that does not fit is deleted with ``--reject NAME``, which
also remembers its Commons file, so it never comes back.

    python tools/fetch_pictures.py                 fetch what is missing
    python tools/fetch_pictures.py --sheet THEME   a contact sheet of a theme (sheet-THEME.jpg)
    python tools/fetch_pictures.py --reject NAME   delete a picture and never fetch it again
"""
import argparse
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "content" / "pictures"
CREDITS = OUT / "credits.json"
REJECTED = OUT / "rejected.txt"
API = "https://commons.wikimedia.org/w/api.php"
UA = "unseenet-demo/0.1 (https://github.com/unseenet/unseenet-demo)"
WANT = {"guineapigs": 7, "bees": 8, "bread": 8, "radio": 6, "hiking": 6, "night sky": 6,
        "sea": 5, "mountains": 5, "garden": 6, "home": 5, "town": 5,
        "autumn": 6, "winter": 6, "spring": 6, "summer": 6}
QUERIES = {
    "guineapigs": ["Cavia porcellus domestic", "domestic guinea pig", "guinea pig pet animal",
                   "guinea pigs eating hay", "guinea pig rodent pet", "Meerschweinchen", "cobaye"],
    "bees": ["honey bee flower", "beehive apiary", "beekeeper frame honeycomb", "honey jar"],
    "bread": ["sourdough bread", "bread loaves bakery", "rye bread", "cinnamon buns", "bread dough"],
    "radio": ["amateur radio antenna", "yagi antenna", "Morse key telegraph", "vintage radio receiver",
              "shortwave receiver", "radio valve tube", "antenna mast", "Amateurfunk", "radio transceiver front panel"],
    "hiking": ["hiking trail forest", "footpath countryside", "walking path hills"],
    "night sky": ["milky way night sky", "starry sky", "full moon", "meteor shower"],
    "sea": ["sea cliffs coast", "beach waves", "coastline lighthouse"],
    "mountains": ["mountain lake", "mountain landscape", "alpine meadow"],
    "garden": ["vegetable garden", "flower garden", "allotment garden"],
    "home": ["cup of tea", "reading book chair", "cozy kitchen", "bookshelf"],
    "town": ["old town street", "market square town", "village street"],
    "autumn": ["autumn leaves", "autumn forest", "autumn park"],
    "winter": ["snow forest winter", "snowy village", "frost leaves winter", "snow covered trees", "icicles"],
    "spring": ["spring flowers meadow", "cherry blossom", "spring forest green"],
    "summer": ["summer meadow", "sunflowers field", "summer lake", "wild flowers summer", "wheat field summer"],
}
NOT = re.compile(r"\b(YPM|specimen|MET DT|painting|portrait|museum|drawing|engraving|illustration|"
                 r"poster|stamp|coin|map|diagram|logo|selfie|wedding|man|woman|girl|boy|people|"
                 r"protest|demonstration|rally|march|riot|war|military|army|police|election|"
                 r"politic\w*|campaign|memorial|funeral|church|mosque|synagogue|temple|"
                 r"astronaut|ISS|expedition|crew|NASA|anagallis|pimpernel)\b", re.I)


# Commons categories that mean a painting, a drawing, a museum object or people
ART = re.compile(r"(paintings|drawings|artworks|illustrations|engravings|museum|collection|"
                 r"portraits|people|men|women|children|impressionism|oil on canvas|"
                 r"scanned|historical images)", re.I)


def accepted(licence: str) -> bool:
    """Public domain, CC0, or plain CC BY of any version - no SA, NC or ND."""
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


def candidates(query: str):
    res = get({"action": "query", "generator": "search", "gsrsearch": f"filetype:bitmap {query}",
               "gsrnamespace": 6, "gsrlimit": 40, "prop": "imageinfo",
               "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 1024,
               "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Artist|ImageDescription|Categories"})
    for p in sorted(res.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99)):
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = clean(meta.get("LicenseShortName", {}).get("value", ""))
        if info.get("mime") not in ("image/jpeg", "image/png") or info.get("width", 0) < 800:
            continue
        if not 0.6 <= info.get("width", 1) / max(info.get("height", 1), 1) <= 2.0:
            continue                                       # no panoramas or thin strips
        cats = clean(meta.get("Categories", {}).get("value", ""))
        if not accepted(lic) or NOT.search(p["title"]) or ART.search(cats):
            continue                                       # not art, museum objects or people
        yield {"title": p["title"], "page": info.get("descriptionurl"), "url": info.get("thumburl"),
               "license": lic, "license_url": meta.get("LicenseUrl", {}).get("value", ""),
               "author": re.sub(r"^(Unknown author)+$", "Unknown author",
                                clean(meta.get("Artist", {}).get("value", ""))) or "Unknown author",
               "description": clean(meta.get("ImageDescription", {}).get("value", ""))[:200]}


def as_jpeg(data: bytes) -> bytes:
    """The picture as a JPEG of at most 1024 px - under the 1 MiB a demo group and a
    node take per file (the client cleans its metadata when it posts it)."""
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((1024, 1024))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85, optimize=True)
    return out.getvalue()


def write_credits(credits: dict) -> None:
    CREDITS.write_text(json.dumps(credits, indent=2, ensure_ascii=False) + "\n")
    lines = ["# Credits", "", "The pictures in `content/pictures/` come from "
             "[Wikimedia Commons](https://commons.wikimedia.org/) and keep their own licences: "
             "public domain, CC0 or CC BY. They are posted in the demo with their source, "
             "after the client has taken out their metadata.", "",
             "| File | What | By | Licence | Source |", "|---|---|---|---|---|"]
    for name, c in sorted(credits.items()):
        lic = f"[{c['license']}]({c['license_url']})" if c["license_url"] else c["license"]
        what = (c["description"] or c["title"].removeprefix("File:")).replace("|", "/")[:90]
        lines.append(f"| `{Path(c['file']).name}` | {what} | {c['author'].replace('|', '/')[:60]} "
                     f"| {lic} | [{c['title'].removeprefix('File:')}]({c['page']}) |")
    (ROOT / "CREDITS.md").write_text("\n".join(lines) + "\n")


def fetch() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    credits = json.loads(CREDITS.read_text()) if CREDITS.exists() else {}
    rejected = set(REJECTED.read_text().splitlines()) if REJECTED.exists() else set()
    have = {c["title"] for c in credits.values()}
    for theme, want in WANT.items():
        count = sum(1 for c in credits.values() if theme in c.get("themes", []))
        slug = theme.replace(" ", "")
        n = 1
        for query in QUERIES[theme]:
            if count >= want:
                break
            for found in candidates(query):
                if count >= want:
                    break
                if found["title"] in have or found["title"] in rejected:
                    continue
                while f"{slug}-{n}" in credits:
                    n += 1
                name = f"{slug}-{n}"
                req = urllib.request.Request(found["url"], headers={"User-Agent": UA})
                try:
                    with urllib.request.urlopen(req, timeout=60) as r:
                        (OUT / f"{name}.jpg").write_bytes(as_jpeg(r.read()))
                except Exception as exc:  # noqa: BLE001 - one bad file: the next
                    print(f"  {found['title']}: {exc}", file=sys.stderr)
                    continue
                credits[name] = {**found, "file": f"content/pictures/{name}.jpg", "themes": [theme]}
                have.add(found["title"])
                count += 1
                print(f"{name}: {found['title'][:70]} ({found['license']})")
                time.sleep(0.5)                            # be polite to Commons
            time.sleep(1)
        print(f"{theme}: {count} of {want}")
    write_credits(credits)


def sheet(theme: str) -> None:
    from PIL import Image, ImageDraw
    credits = json.loads(CREDITS.read_text())
    names = sorted(n for n, c in credits.items() if theme in c.get("themes", []))
    W, H, cols = 256, 180, 4
    rows = (len(names) + cols - 1) // cols or 1
    out = Image.new("RGB", (cols * W, rows * (H + 18)), "white")
    d = ImageDraw.Draw(out)
    for i, n in enumerate(names):
        im = Image.open(OUT / f"{n}.jpg").convert("RGB")
        im.thumbnail((W - 6, H - 6))
        x, y = (i % cols) * W, (i // cols) * (H + 18)
        out.paste(im, (x + 3, y + 3))
        d.text((x + 4, y + H), n, fill="black")
    path = ROOT / f"sheet-{theme.replace(' ', '')}.jpg"
    out.save(path, quality=80)
    print(path)


def reject(name: str) -> None:
    credits = json.loads(CREDITS.read_text())
    c = credits.pop(name)
    with open(REJECTED, "a") as f:
        f.write(c["title"] + "\n")
    (OUT / f"{name}.jpg").unlink(missing_ok=True)
    write_credits(credits)
    print(f"{name} rejected: {c['title']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sheet", metavar="THEME")
    ap.add_argument("--reject", metavar="NAME", nargs="+")
    a = ap.parse_args()
    if a.sheet:
        sheet(a.sheet)
    elif a.reject:
        for r in a.reject:
            reject(r)
    else:
        fetch()
