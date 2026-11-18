"""Secret picks for guessing games, chosen by the server instead of the model.

Left to choose, the model picks the same few secrets every time: on 2026-11-18 it was
"penguin" (the prompt's own example) or "elephant", two days running. So each
conversation carries a random pick per category, shown in the CURRENT STATE block; once a
pick shows up in the model's notes (it used it), that category gets a fresh one, and a
server-wide memory of recent picks keeps the next game from repeating the last few.
"""

from __future__ import annotations

import random
import re
from collections import deque

ANIMALS = (
    "alligator",
    "anteater",
    "armadillo",
    "bat",
    "bear",
    "beaver",
    "bee",
    "butterfly",
    "camel",
    "cat",
    "caterpillar",
    "cheetah",
    "chicken",
    "chipmunk",
    "cow",
    "crab",
    "crocodile",
    "deer",
    "dog",
    "dolphin",
    "donkey",
    "dragonfly",
    "duck",
    "eagle",
    "elephant",
    "flamingo",
    "fox",
    "frog",
    "giraffe",
    "goat",
    "goldfish",
    "gorilla",
    "hamster",
    "hedgehog",
    "hippo",
    "horse",
    "hummingbird",
    "jellyfish",
    "kangaroo",
    "koala",
    "ladybug",
    "lion",
    "lizard",
    "llama",
    "lobster",
    "monkey",
    "moose",
    "mouse",
    "octopus",
    "ostrich",
    "otter",
    "owl",
    "panda",
    "parrot",
    "peacock",
    "pelican",
    "penguin",
    "pig",
    "polar bear",
    "porcupine",
    "rabbit",
    "raccoon",
    "rhino",
    "seahorse",
    "seal",
    "shark",
    "sheep",
    "skunk",
    "sloth",
    "snail",
    "snake",
    "spider",
    "squirrel",
    "starfish",
    "swan",
    "tiger",
    "turkey",
    "turtle",
    "walrus",
    "whale",
    "wolf",
    "woodpecker",
    "zebra",
)
FOODS = (
    "apple",
    "banana",
    "blueberry",
    "bread",
    "broccoli",
    "carrot",
    "cheese",
    "cookie",
    "corn",
    "cupcake",
    "egg",
    "grapes",
    "hot dog",
    "ice cream",
    "lemon",
    "milk",
    "orange",
    "pancake",
    "pasta",
    "peanut butter",
    "pear",
    "pickle",
    "pizza",
    "popcorn",
    "potato",
    "pumpkin",
    "strawberry",
    "taco",
    "tomato",
    "watermelon",
)
THINGS = (
    "backpack",
    "ball",
    "balloon",
    "bed",
    "bicycle",
    "boat",
    "book",
    "broom",
    "bus",
    "candle",
    "chair",
    "clock",
    "crayon",
    "drum",
    "fire truck",
    "guitar",
    "hat",
    "kite",
    "lamp",
    "pillow",
    "rainbow",
    "rocket",
    "scissors",
    "shoe",
    "slide",
    "spoon",
    "teddy bear",
    "toothbrush",
    "train",
    "umbrella",
)
CATEGORIES: dict[str, tuple[str, ...]] = {
    "animal": ANIMALS,
    "food": FOODS,
    "thing": THINGS,
}

# Server-wide: the last picks used in any conversation, so back-to-back games (and the
# next day's, while the server runs) get different secrets.
_RECENT: dict[str, deque[str]] = {
    c: deque(maxlen=len(v) // 2) for c, v in CATEGORIES.items()
}


class GamePicks:
    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        self.picks: dict[str, str] = {c: self._fresh(c) for c in CATEGORIES}

    def _fresh(self, category: str) -> str:
        recent = _RECENT[category]
        pool = [x for x in CATEGORIES[category] if x not in recent]
        pick = self._rng.choice(pool or CATEGORIES[category])
        recent.append(pick)
        return pick

    def mark_used(self, notes: str) -> None:
        """After a reply: a pick named in the notes is in use, so the next game gets another."""
        if not notes:
            return
        low = notes.lower()
        for category, pick in list(self.picks.items()):
            if re.search(rf"\b{re.escape(pick)}\b", low):
                self.picks[category] = self._fresh(category)

    def line(self) -> str:
        p = self.picks
        return (
            "GAME PICKS: only when you choose a NEW secret for a guessing game (your notes have"
            f" no secret yet), use the one for its kind: animal: {p['animal']}; food:"
            f" {p['food']}; thing: {p['thing']}. Unless the child asks for something else."
            " A secret already in your notes never changes."
        )
