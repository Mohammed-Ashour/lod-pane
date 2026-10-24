"""LOD lookup and local vocabulary. Shared by Word's server and LibreOffice."""
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import ssl
import sys
import unicodedata
from urllib.error import URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

API = "https://lod.lu/api/lb"
LANGUAGES = ("en", "fr", "de")


class DictionaryUnavailable(Exception):
    pass


def data_directory():
    if os.environ.get("LOD_PANE_DATA_DIR"):
        return Path(os.environ["LOD_PANE_DATA_DIR"])
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/LOD pane"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "LOD pane"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "lod-pane"


@contextmanager
def database():
    directory = data_directory()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    connection = sqlite3.connect(str(directory / "vocabulary.sqlite3"), timeout=5)
    try:
        with connection:
            connection.execute("CREATE TABLE IF NOT EXISTS words (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            yield connection
    finally:
        connection.close()


def preferences(changes=None):
    defaults = {"theme": "light", "language": "en"}
    if changes is not None:
        if not isinstance(changes, dict) or set(changes) - set(defaults):
            raise ValueError("Unknown preference.")
        if "theme" in changes and changes["theme"] not in ("light", "dark"):
            raise ValueError("Choose light or dark.")
        if "language" in changes and changes["language"] not in LANGUAGES:
            raise ValueError("Choose English, French, or German.")
    with database() as db:
        if changes:
            db.executemany("INSERT OR REPLACE INTO settings VALUES (?, ?)", changes.items())
        defaults.update(dict(db.execute("SELECT key, value FROM settings")))
    return defaults


def has_preferences():
    """True once the user has ever chosen a theme or language."""
    with database() as db:
        return db.execute("SELECT 1 FROM settings LIMIT 1").fetchone() is not None


def normalize_word(value):
    if not isinstance(value, str):
        raise ValueError("Select one Luxembourgish word.")
    value = unicodedata.normalize("NFC", value).strip().strip("\"'„“”‘’«».,;:!?()[]{}")
    if len(value) > 80 or not re.fullmatch(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*", value, re.UNICODE):
        raise ValueError("Select one word, or type it in the search field.")
    return value


def clean(value):
    return " ".join(html.unescape(re.sub(r"<[^>]*>", "", str(value or ""))).split())


def context_excerpt(text, word, limit=1000):
    """Keep the selected word inside a bounded paragraph excerpt."""
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    index = text.casefold().find(str(word or "").strip().casefold())
    if index < 0:
        return text[:limit].rstrip()
    room_before = max(0, limit - len(word)) // 2
    start = max(0, min(index - room_before, len(text) - limit))
    return text[start:start + limit].strip()


def parts_text(parts):
    text = ""
    for part in parts or []:
        value = parts_text(part["parts"]) if part.get("parts") else clean(part.get("content"))
        if not value:
            continue
        if part.get("type") == "semanticClarifier":
            value = "(" + value + ")"
        join = not text or part.get("joinWithPreviousWord") or value[0] in ",.;:!?)]" or text.endswith(("'", "’"))
        separator = "" if join else " · " if part.get("type") == "translation" else " "
        if part.get("partOfSpeech"):
            value += " (" + clean(part["partOfSpeech"]).lower() + ")"
        text += separator + value
    return text


def fetch_json(path):
    request = Request(API + path, headers={"Accept": "application/json", "User-Agent": "LOD-pane/0.1"})
    try:
        context = ssl.create_default_context()
        # Python.org and LibreOffice's bundled macOS Python may lack an OpenSSL CA
        # path. Use macOS's shipped CA bundle; never disable HTTPS verification.
        if sys.platform == "darwin" and not ssl.get_default_verify_paths().cafile and Path("/etc/ssl/cert.pem").is_file():
            context.load_verify_locations("/etc/ssl/cert.pem")
        with urlopen(request, timeout=8, context=context) as response:
            payload = response.read(2_000_001)
        if len(payload) > 2_000_000:
            raise ValueError("Oversized dictionary response")
        result = json.loads(payload)
        if not isinstance(result, dict):
            raise ValueError("Invalid dictionary response")
        return result
    except (OSError, URLError, ValueError) as error:
        raise DictionaryUnavailable("LOD is unavailable. Check your internet connection and try again.") from error


def part_of_speech(tag):
    return {"SUBST": "noun", "SUBST+N": "noun · neuter", "SUBST+M": "noun · masculine", "SUBST+F": "noun · feminine", "ADJ": "adjective", "VRB": "verb", "ADV": "adverb", "PREP": "preposition"}.get(tag, tag)


def normalize_entry(raw):
    if not isinstance(raw, dict) or not raw.get("lod_id") or not raw.get("lemma"):
        raise DictionaryUnavailable("LOD returned an incomplete entry. Try again later.")
    senses = []
    for micro in raw.get("microStructures", []):
        for unit in micro.get("grammaticalUnits", []):
            for meaning in unit.get("meanings", []):
                translations = {lang: parts_text(value.get("parts")) for lang, value in meaning.get("targetLanguages", {}).items() if lang in LANGUAGES}
                examples = [parts_text(item.get("parts")) for item in meaning.get("examples", [])]
                forms = [clean(item.get("content")) for item in meaning.get("inflection", {}).get("forms", [])]
                grammar = " · ".join(filter(None, [clean(meaning.get("declensionInfo")), ", ".join(forms)]))
                senses.append({"id": clean(meaning.get("meaningID")) or str(len(senses) + 1), "translations": translations, "grammar": grammar, "example": next(filter(None, examples), "")})
    if not senses:
        raise DictionaryUnavailable("This LOD entry has no supported meanings yet.")
    basic = raw.get("tables", {}).get("adjDeclension", {}).get("basicForms", {})
    adjective_forms = " · ".join(label + ": " + clean(basic[name]) for name, label in (("comparative", "Comparative"), ("superlative", "Superlative")) if basic.get(name))
    for sense in senses:
        if not sense["grammar"]:
            sense["grammar"] = adjective_forms
    tag = clean(raw.get("partOfSpeechLabel") or raw.get("partOfSpeech"))
    pos = part_of_speech(tag)
    return {"id": clean(raw["lod_id"]), "word": clean(raw["lemma"]), "pos": pos, "url": "https://lod.lu/artikel/" + quote(raw["lod_id"], safe=""), "senses": senses}


@lru_cache(maxsize=128)
def entry(entry_id):
    if not isinstance(entry_id, str) or not re.fullmatch(r"[\w-]{1,100}", entry_id):
        raise ValueError("Invalid dictionary entry.")
    try:
        return normalize_entry(fetch_json("/entry/" + quote(entry_id, safe="")).get("entry"))
    except (AttributeError, KeyError, TypeError) as error:
        raise DictionaryUnavailable("LOD returned an unreadable entry. Try again later.") from error


def saved_words():
    with database() as db:
        return [json.loads(row[0]) for row in db.execute("SELECT value FROM words ORDER BY rowid DESC")]


def lookup(value):
    query = normalize_word(value)
    try:
        results = fetch_json("/search?" + urlencode({"lang": "lb", "query": query})).get("results")
        if not isinstance(results, list):
            raise DictionaryUnavailable("LOD returned an unreadable search result.")
        candidates = []
        exact = []
        lemmas = []
        for item in results[:20]:
            if not isinstance(item, dict):
                continue
            identifier = item.get("article_id") or item.get("id")
            word = clean(item.get("word_lb") or item.get("lemma"))
            if not identifier or not word:
                continue
            candidate = {"id": identifier, "word": word, "pos": part_of_speech(clean(item.get("pos")))}
            candidates.append(candidate)
            if query.casefold() == word.casefold():
                lemmas.append(candidate)
            matches = [word] + [clean(match) for match in item.get("matches", [])]
            if query.casefold() in [match.casefold() for match in matches]:
                exact.append(candidate)
        # Prefer literal headwords over other entries' inflection matches.
        exact = lemmas or exact
        # Never silently choose between homonyms or partial search results.
        if len(exact) == 1:
            return {"entry": entry(exact[0]["id"]), "candidates": [], "offline": False}
        return {"entry": None, "candidates": exact or candidates, "offline": False}
    except DictionaryUnavailable:
        cached = {item["entry"]["id"]: item["entry"] for item in saved_words() if item["entry"]["word"].casefold() == query.casefold()}
        if len(cached) == 1:
            return {"entry": next(iter(cached.values())), "candidates": [], "offline": True}
        raise


def save_word(payload):
    if not isinstance(payload, dict):
        raise ValueError("Invalid saved word.")
    identifier, sense_id = payload.get("entryId"), payload.get("senseId")
    # Saved entries are trusted dictionary snapshots, not arbitrary client HTML/data.
    selected = next((item["entry"] for item in saved_words() if item["entry"]["id"] == identifier), None)
    if selected is None:
        selected = entry(identifier)
    if not any(sense["id"] == sense_id for sense in selected["senses"]):
        raise ValueError("Choose a meaning before saving.")
    base_updated = payload.get("baseUpdated")
    if base_updated is not None and (not isinstance(base_updated, str) or len(base_updated) > 80):
        raise ValueError("Invalid saved word version.")
    note, context = payload.get("note", ""), payload.get("context", "")
    if not isinstance(note, str) or len(note) > 2000 or not isinstance(context, str) or len(context) > 1000:
        raise ValueError("The note or sentence is too long.")
    if payload.get("destination") not in ("Study", "Favorites"):
        raise ValueError("Choose Study or Favorites.")
    key = identifier + "#" + sense_id
    value = {"key": key, "entry": selected, "senseId": sense_id, "note": note, "context": context, "destination": payload["destination"], "updated": datetime.now(timezone.utc).isoformat()}
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT value FROM words WHERE key = ?", (key,)).fetchone()
        current_updated = json.loads(row[0]).get("updated") if row else None
        if current_updated != base_updated:
            raise ValueError("This saved word changed in another pane. Reopen it and try again.")
        db.execute("INSERT OR REPLACE INTO words VALUES (?, ?)", (key, json.dumps(value, ensure_ascii=False)))
    return value


def delete_word(key, base_updated=None):
    if not isinstance(key, str) or not 1 <= len(key) <= 220:
        raise ValueError("Invalid saved word.")
    if base_updated is not None and (not isinstance(base_updated, str) or len(base_updated) > 80):
        raise ValueError("Invalid saved word version.")
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT value FROM words WHERE key = ?", (key,)).fetchone()
        if row and json.loads(row[0]).get("updated") != base_updated:
            raise ValueError("This saved word changed in another pane. Reopen Saved and try again.")
        db.execute("DELETE FROM words WHERE key = ?", (key,))
