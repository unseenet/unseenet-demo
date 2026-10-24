"""Posts worked out from the date, so they are true and new every week.

Each function takes the date of the week's run and gives ``(subject, body)`` for one of
the demo's people. The subject names the week, so a post is never the same twice in a
year. The moon is computed; the rest comes from what each month brings (in the
northern hemisphere, where the demo's village is).
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

SYNODIC = 29.530588853                                  # days, new moon to new moon
NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)   # a known new moon

# meteor showers: (name, month, day of peak, meteors an hour at best, radiant)
SHOWERS = [("Quadrantids", 1, 4, 80, "Boötes"), ("Lyrids", 4, 22, 18, "Lyra"),
           ("Eta Aquariids", 5, 6, 50, "Aquarius"), ("Perseids", 8, 12, 100, "Perseus"),
           ("Orionids", 10, 21, 20, "Orion"), ("Leonids", 11, 17, 15, "Leo"),
           ("Geminids", 12, 14, 120, "Gemini"), ("Ursids", 12, 22, 10, "Ursa Minor")]

BEES = {1: "The hives are quiet. I knock, listen, and leave them be - the cluster keeps itself warm.",
        2: "Checking the weight of the hives by lifting the back: heavy is good. Light ones get fondant.",
        3: "First cleansing flights on a sunny day. The willow catkins are the first real food.",
        4: "Spring inspection: brood, queen, stores. The colonies build up fast now.",
        5: "Swarm season. Every week I look for queen cells, and every week I am too late somewhere.",
        6: "Supers on. The lime trees are about to flower, and the bees know it.",
        7: "The honey flow. Frames getting heavy, bees getting grumpy in the heat.",
        8: "Harvest time - extracting, straining, jars everywhere. The kitchen floor is sticky again.",
        9: "Feeding sugar syrup for winter, and treating against varroa.",
        10: "Mouse guards on. The last ivy flowers keep them busy on warm afternoons.",
        11: "Wrapping up: hives strapped down against the wind, roofs weighted.",
        12: "Nothing to do but wait - and melt old comb into candles."}

BREAD = {1: "Rye season. Dark, dense, caraway - the bread that gets you through January.",
         2: "Semlor for Shrove Tuesday: cardamom buns, almond paste, far too much cream.",
         3: "Hot cross buns are coming. Testing the spice mix every morning until it is right.",
         4: "Lighter loaves for spring, with the first wild garlic folded in.",
         5: "Rhubarb from the garden, so rhubarb buns. Tart, sweet, gone by noon.",
         6: "Focaccia for long evenings outside, with rosemary and too much olive oil.",
         7: "Too hot for the oven at noon, so I bake at four in the morning. Peaches on brioche.",
         8: "Blueberry season - the cinnamon buns turn purple and nobody complains.",
         9: "The new grain is in. The first loaf from this year's flour always tastes of the field.",
         10: "Apple and walnut loaves, and the cardamom knots everyone asks for when it gets dark.",
         11: "Starting the Christmas stollen. It needs weeks to be good.",
         12: "Saffron buns and gingerbread. The bakery smells like December."}

RADIO = {1: "Long winter nights: the low bands are open late, and you hear the other side of the world.",
         2: "Still good on 80 and 40 metres after dark. Contest weekend - the bands are full.",
         3: "Around the equinox the paths between the hemispheres open up. Best time of year for DX.",
         4: "Spring propagation: 20 metres open from morning to night.",
         5: "Sporadic-E is starting - suddenly 6 metres is full of stations from all over Europe.",
         6: "Midsummer Sporadic-E at its best. Short, surprising openings; keep the radio on.",
         7: "Thunderstorm static on the low bands, so it is the higher bands and a lot of patience.",
         8: "Late summer: Sporadic-E fading, the bands a bit sleepy. A good month for antenna work.",
         9: "The autumn equinox brings the long paths back. Worked Japan on 20 metres this week.",
         10: "October: the high bands come alive in daylight, the low bands at night. My favourite month.",
         11: "Grey line in the late afternoon - the sunset line carries signals a very long way.",
         12: "Christmas: everybody is on the air, and the bands are full of greetings."}

PIGS = {"winter": "Cold outside, so Pepper and Biscuit stay in. Extra hay, and a fleece in their hideout.",
        "spring": "Spring greens at last: dandelion leaves are back on the menu, a few at a time.",
        "summer": "Hot days: the cage away from the window, a cool tile to lie on, and fresh water twice a day.",
        "autumn": "Autumn moult - fluff everywhere. Brushing every evening, and fresh hay to make up for it."}


def season(d: date) -> str:
    return {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
            6: "summer", 7: "summer", 8: "summer"}.get(d.month, "autumn")


def week(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"week {w}, {y}"


def moon(d: date) -> tuple[str, float, date]:
    """The moon's phase on a day: its name, how much is lit (0-1), and the next full moon."""
    t = datetime(d.year, d.month, d.day, 21, tzinfo=timezone.utc)     # in the evening
    age = ((t - NEW_MOON).total_seconds() / 86400) % SYNODIC
    lit = (1 - math.cos(2 * math.pi * age / SYNODIC)) / 2
    names = [(1.0, "new moon"), (6.4, "waxing crescent"), (8.4, "first quarter"),
             (13.8, "waxing gibbous"), (15.8, "full moon"), (21.1, "waning gibbous"),
             (23.1, "last quarter"), (28.5, "waning crescent"), (SYNODIC, "new moon")]
    name = next(n for limit, n in names if age < limit)
    full = d + timedelta(days=round((SYNODIC / 2 - age) % SYNODIC))
    return name, lit, full


def ines(d: date) -> tuple[str, str]:
    name, lit, full = moon(d)
    text = f"The moon is a {name} this evening, {round(lit * 100)}% lit. Next full moon: {full:%d %B}."
    soon = [(n, date(d.year, m, day), rate, where) for n, m, day, rate, where in SHOWERS]
    soon = [s for s in soon if 0 <= (s[1] - d).days <= 14]
    if soon:
        n, peak, rate, where = soon[0]
        dark = "a dark sky, good" if lit < 0.4 else "a bright moon, so fewer"
        text += (f"\n\nThe {n} peak on {peak:%d %B}: up to {rate} meteors an hour from {where}, "
                 f"with {dark} chances. I'll be out with a blanket and a thermos.")
    elif lit < 0.3:
        text += "\n\nA dark week - the best time for the Milky Way, if the clouds let us."
    else:
        text += "\n\nToo bright for faint things, so I'm looking at the moon itself through the binoculars."
    return f"The sky this week ({week(d)})", text


def tomas(d: date) -> tuple[str, str]:
    return f"At the hives ({week(d)})", BEES[d.month]


def nadia(d: date) -> tuple[str, str]:
    return f"From the oven ({week(d)})", BREAD[d.month]


def ole(d: date) -> tuple[str, str]:
    return f"On the bands ({week(d)})", RADIO[d.month]


def mira(d: date) -> tuple[str, str]:
    return f"Pepper and Biscuit ({week(d)})", PIGS[season(d)]


FOR = {"ines": ines, "tomas": tomas, "nadia": nadia, "ole": ole, "mira": mira}
