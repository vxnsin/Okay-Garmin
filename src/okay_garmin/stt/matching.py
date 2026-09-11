"""Matching spoken text against configured commands.

Keeps v1's SequenceMatcher approach -- it is good enough and has no
dependencies -- but adds German normalisation and picks the *best* match
instead of the first one over the threshold. With the old first-past-the-post
rule, adding "video speichern und hochladen" after "video speichern" made the
longer command unreachable.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

UMLAUTS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}

FILLERS = {
    "bitte", "mal", "jetzt", "doch", "eben", "kurz", "also",
    "please", "now", "just",
}

NUMBER_WORDS = {
    "null": "0", "eins": "1", "ein": "1", "eine": "1", "zwei": "2", "drei": "3",
    "vier": "4", "fünf": "5", "fuenf": "5", "sechs": "6", "sieben": "7",
    "acht": "8", "neun": "9", "zehn": "10",
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
}


SLOT = "{}"


def fold(word: str) -> str:
    """Lowercase and strip accents/punctuation, but keep the word.

    Unlike normalize(), this maps one input word to one output word, so a
    folded token list stays aligned with the original. That alignment is what
    lets a slot command recover the user's actual words for the free-text part
    -- "spiel {}" has to hand Spotify what was really said, not a normalised
    version of it.
    """
    word = word.lower()
    for src, dst in UMLAUTS.items():
        word = word.replace(src, dst)
    word = unicodedata.normalize("NFKD", word)
    word = "".join(ch for ch in word if not unicodedata.combining(ch))
    return re.sub(r"[^\w]+", "", word)


def normalize(text: str) -> str:
    """Lowercase, fold umlauts, strip punctuation, drop fillers, digitise numbers."""
    text = text.lower().strip()
    for src, dst in UMLAUTS.items():
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s]+", " ", text)

    words = []
    for word in text.split():
        if word in FILLERS:
            continue
        words.append(NUMBER_WORDS.get(word, word))
    return " ".join(words)


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def phrase_score(text: str, phrase: str) -> float:
    """Best similarity of `phrase` against any same-length window of `text`.

    A window of n+1 words is also tried so an inserted filler word doesn't sink
    an otherwise clean match, and n-1 for the same reason -- but only from three
    words up. On a two-word command the shorter window is a single word, which
    is far too permissive: "wiederholen" alone would then satisfy "wiederholen
    an", and any sentence containing the verb would fire the command.
    """
    text = normalize(text)
    phrase = normalize(phrase)
    if not text or not phrase:
        return 0.0
    if phrase in text:
        return 1.0

    words = text.split()
    n = len(phrase.split())

    widths = {n, n + 1}
    if n >= 3:
        widths.add(n - 1)

    best = similarity(text, phrase)
    for width in widths:
        for i in range(len(words) - width + 1):
            window = " ".join(words[i : i + width])
            best = max(best, similarity(window, phrase))
    return best


def contains(text: str, phrase: str, threshold: float = 0.72) -> bool:
    return phrase_score(text, phrase) >= threshold


def slot_score(text: str, phrase: str) -> tuple[float, str]:
    """Match a phrase containing a {} slot, e.g. "spiel {}".

    Returns (score, argument). The words around the slot must match; whatever
    sits in the slot is returned verbatim, because it is a song or playlist
    name that must not be normalised away.
    """
    prefix, _, suffix = phrase.partition(SLOT)
    original = text.split()
    folded = [fold(word) for word in original]
    folded = [word for word in folded if word]

    prefix_words = [fold(w) for w in prefix.split() if fold(w)]
    suffix_words = [fold(w) for w in suffix.split() if fold(w)]

    # There must be at least one word left over to fill the slot.
    if len(folded) < len(prefix_words) + len(suffix_words) + 1:
        return 0.0, ""

    score = 1.0
    if prefix_words:
        score = min(
            score,
            similarity(" ".join(folded[: len(prefix_words)]), " ".join(prefix_words)),
        )
    if suffix_words:
        tail = folded[len(folded) - len(suffix_words) :]
        score = min(score, similarity(" ".join(tail), " ".join(suffix_words)))

    start = len(prefix_words)
    end = len(original) - len(suffix_words)
    argument = " ".join(original[start:end]).strip(" ,.")
    if not argument:
        return 0.0, ""
    return score, argument


SHORT_PHRASE_CHARS = 12
SHORT_PHRASE_PENALTY = 0.02


def effective_threshold(phrase: str, base: float) -> float:
    """Demand a higher score from short phrases.

    Character similarity is forgiving on short strings: "weiter" scores 0.83
    against "wetter", which would let an unrelated sentence fire a command.
    Every character below SHORT_PHRASE_CHARS raises the bar a little.
    """
    length = len(normalize(phrase.replace(SLOT, "")))
    if length >= SHORT_PHRASE_CHARS:
        return base
    return min(0.95, base + (SHORT_PHRASE_CHARS - length) * SHORT_PHRASE_PENALTY)


def best_command(text: str, commands: list[dict], threshold: float = 0.72):
    """Return (command, score, argument) for the best match.

    `argument` is the free text captured by a {} slot, and "" for plain
    commands. On no match the command is None.

    On a tie the longer phrase wins. Both "video speichern" and "video
    speichern und hochladen" score 1.0 against the latter being spoken, and
    without the length tiebreak the shorter one would shadow the longer one
    permanently.
    """
    best: dict | None = None
    best_score = 0.0
    best_length = 0
    best_argument = ""

    for command in commands:
        if not command.get("enabled", True):
            continue
        phrases = [command.get("command", "")]
        phrases.extend(command.get("aliases") or [])
        for phrase in phrases:
            if not phrase.strip():
                continue

            if SLOT in phrase:
                score, argument = slot_score(text, phrase)
            else:
                score, argument = phrase_score(text, phrase), ""

            length = len(normalize(phrase.replace(SLOT, "")))
            # A phrase only counts if it clears its own bar; the reported score
            # is still the raw one, so the UI shows what was actually measured.
            if score < effective_threshold(phrase, threshold):
                best_score = max(best_score, score)
                continue

            if score > best_score + 1e-9 or (
                abs(score - best_score) < 1e-9 and length > best_length
            ):
                best_score, best_length, best, best_argument = score, length, command, argument

    if best is not None:
        return best, best_score, best_argument
    return None, best_score, ""
