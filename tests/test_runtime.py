"""Run: python3 tests/test_runtime.py. Standard library only; no live LOD required."""
from contextlib import contextmanager
from copy import deepcopy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from unittest.mock import patch
from xml.etree import ElementTree
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import lodpane
import server

FIXTURE = json.loads((ROOT / "tests/fixtures/wieder.json").read_text())


def fixture_fetch(path):
    if path.startswith("/entry/"):
        if path.endswith("MISSING1"):
            raise lodpane.DictionaryUnavailable("Offline for test")
        if path.endswith("HEEM1"):
            result = deepcopy(FIXTURE)
            result["entry"].update(lod_id="HEEM1", lemma="heem", partOfSpeechLabel="ADV")
            result["entry"]["microStructures"][0]["grammaticalUnits"][0]["meanings"] = [{"meaningID": "HEEM1UNI1", "targetLanguages": {"en": {"parts": [{"content": "home"}]}, "fr": {"parts": [{"content": "à la maison"}]}}, "examples": []}]
            return result
        return FIXTURE
    if "query=offline" in path:
        raise lodpane.DictionaryUnavailable("Offline for test")
    if "query=nothing" in path:
        return {"results": []}
    if "query=heem" in path:
        return {"results": [{"id": "HEEM1", "word_lb": "heem", "pos": "ADV"}]}
    if "query=ambiguous" in path:
        return {"results": [{"id": "A1", "word_lb": "ambiguous"}, {"id": "A2", "word_lb": "ambiguous"}]}
    return {"results": [{"id": "WIEDER1", "word_lb": "Wieder", "pos": "SUBST+N"}, {"id": "WIEDEREN1", "word_lb": "wiederen", "matches": ["<strong>wieder</strong>"]}]}


@contextmanager
def temporary_data():
    with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOD_PANE_DATA_DIR": directory}):
        lodpane.entry.cache_clear()
        yield
        lodpane.entry.cache_clear()


def run():
    assert lodpane.normalize_word("  ‘fläisseg’! ") == "fläisseg"
    assert lodpane.normalize_word("fla\u0308isseg") == "fläisseg"
    assert lodpane.parts_text([{"type": "translation", "content": "hard-working"}, {"type": "translation", "content": "diligently", "partOfSpeech": "Adverb"}]) == "hard-working · diligently (adverb)"
    for invalid in ("", "two words", "x" * 81, "<script>", 42):
        try:
            lodpane.normalize_word(invalid)
            assert False, "Invalid lookup accepted"
        except ValueError:
            pass
    assert lodpane.parts_text([{"content": "d'"}, {"content": "Wieder", "joinWithPreviousWord": True}, {"content": ","}, {"content": "schéin"}]) == "d'Wieder, schéin"
    long_paragraph = "x" * 1200 + " Wieder"
    excerpt = lodpane.context_excerpt(long_paragraph, "Wieder")
    assert len(excerpt) == 1000 and "Wieder" in excerpt
    normalized = lodpane.normalize_entry(FIXTURE["entry"])
    assert normalized["word"] == "Wieder" and normalized["pos"] == "noun · neuter"
    assert len(normalized["senses"]) == 3
    assert normalized["senses"][0]["translations"]["en"] == "weather"
    assert normalized["senses"][0]["grammar"] == "kee Pluriel"
    assert "Wiederen" in normalized["senses"][1]["grammar"]
    assert normalized["senses"][0]["example"].startswith("wa schéint Wieder")
    with temporary_data(), patch.object(lodpane, "fetch_json", side_effect=fixture_fetch):
        result = lodpane.lookup("Wieder")
        assert result["entry"]["id"] == "WIEDER1", "Literal lemma must beat an inflection match"
        assert len(lodpane.lookup("ambiguous")["candidates"]) == 2
        assert not lodpane.lookup("nothing")["candidates"]
        assert lodpane.preferences() == {"theme": "light", "language": "en"}
        lodpane.preferences({"theme": "dark", "language": "fr"})
        assert lodpane.preferences()["theme"] == "dark"
        payload = {"entryId": "WIEDER1", "senseId": normalized["senses"][0]["id"], "note": "A memory cue <not HTML>.", "context": "", "destination": "Study"}
        saved = lodpane.save_word(payload)
        assert len(lodpane.saved_words()) == 1 and saved["context"] == ""
        updated = lodpane.save_word(dict(payload, baseUpdated=saved["updated"], note="Updated.", context="Only opted-in text.", destination="Favorites"))
        assert len(lodpane.saved_words()) == 1 and lodpane.saved_words()[0]["note"] == "Updated."
        try:
            lodpane.save_word(dict(payload, baseUpdated=saved["updated"], note="Stale."))
            assert False, "Stale save accepted"
        except ValueError as error:
            assert "another pane" in str(error)
        second = dict(payload, senseId=normalized["senses"][1]["id"])
        lodpane.save_word(second)
        assert len(lodpane.saved_words()) == 2, "Distinct senses must not overwrite one another"
        with patch.object(lodpane, "fetch_json", side_effect=lodpane.DictionaryUnavailable("Offline")):
            assert lodpane.lookup("Wieder")["offline"] is True
            lodpane.entry.cache_clear()
            offline_saved = lodpane.save_word(dict(payload, baseUpdated=updated["updated"], note="Offline edit."))
            assert offline_saved["note"] == "Offline edit."
            try:
                lodpane.lookup("unknown")
                assert False
            except lodpane.DictionaryUnavailable:
                pass
        for change in ({"senseId": "missing"}, {"note": "x" * 2001}, {"context": "x" * 1001}, {"destination": "elsewhere"}):
            try:
                lodpane.save_word(dict(payload, baseUpdated=offline_saved["updated"], **change))
                assert False, "Invalid save accepted"
            except ValueError:
                pass
        try:
            lodpane.delete_word(saved["key"], saved["updated"])
            assert False, "Stale delete accepted"
        except ValueError:
            pass
        current = next(item for item in lodpane.saved_words() if item["key"] == saved["key"])
        lodpane.delete_word(saved["key"], current["updated"])
        assert len(lodpane.saved_words()) == 1
        remaining = lodpane.saved_words()[0]
        # Exercise the real request handler without requiring a trusted test certificate.
        http = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = Thread(target=http.serve_forever, daemon=True)
        thread.start()
        def request(method, path, value=None, headers=None):
            connection = HTTPConnection("127.0.0.1", http.server_port)
            h = {"Host": "localhost:" + str(http.server_port), "X-LOD-Pane": "1", **(headers or {})}
            body = None if value is None else json.dumps(value)
            if body is not None:
                h.setdefault("Content-Type", "application/json")
            connection.request(method, path, body, h)
            response = connection.getresponse()
            status, content = response.status, response.read()
            connection.close()
            return status, content
        try:
            assert request("GET", "/api/lookup?word=Wieder")[0] == 200
            assert request("GET", "/api/words")[0] == 200
            assert request("GET", "/api/words", headers={"X-LOD-Pane": ""})[0] == 403
            assert request("POST", "/api/delete", {"key": remaining["key"], "baseUpdated": remaining["updated"]}, {"Origin": "https://evil.example"})[0] == 403
            assert request("GET", "/api/words", headers={"Host": "evil.example"})[0] == 403
            assert request("POST", "/api/save", payload, {"Content-Type": "text/plain"})[0] == 415
            assert request("GET", "/../../lodpane.py")[0] == 404
            assert request("GET", "/api/lookup?word=two%20words")[0] == 400
            assert request("GET", "/api/lookup?word=offline")[0] == 503
            assert request("POST", "/api/save", payload)[0] == 200
            assert request("GET", "/")[0] == 200
        finally:
            http.shutdown(); http.server_close(); thread.join()
    # Package structure and XML contracts are checked independently of installed hosts.
    import importlib.util
    spec = importlib.util.spec_from_file_location("builder", ROOT / "tools/build.py")
    builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder); builder.main()
    with ZipFile(ROOT / "dist/lod-pane.oxt") as archive:
        assert archive.read("LICENSE") == (ROOT / "LICENSE").read_bytes()
        assert "pythonpath/lodpane.py" in archive.namelist()
        import struct
        assert struct.unpack(">II", archive.read("sidebar-icon.png")[16:24]) == (24, 24)
        import re
        assert re.search(rb"<version value=\"\d+\.\d+\.\d+\"/>", archive.read("description.xml"))
        assert archive.read("panel.py") == (ROOT / "libreoffice/panel.py").read_bytes()
        assert b"sidebar-icon.png" in archive.read("Sidebar.xcu")
        for name in archive.namelist():
            if name.endswith((".xml", ".xcu", ".component")):
                ElementTree.fromstring(archive.read(name))
        assert archive.read("pythonpath/lodpane.py") == (ROOT / "lodpane.py").read_bytes()
    manifest = ElementTree.parse(ROOT / "dist/word-manifest.xml")
    ns = {"o": "http://schemas.microsoft.com/office/appforoffice/1.1"}
    assert manifest.find("o:Permissions", ns).text == "ReadWriteDocument"
    assert manifest.find("o:DefaultSettings/o:SourceLocation", ns).attrib["DefaultValue"].endswith("/word.html")
    with ZipFile(ROOT / "dist/lod-pane-word.zip") as archive:
        expected = {"LICENSE", "server.py", "lodpane.py", "SETUP.md", "START-HERE.txt", "tools/install_word.py",
                    "word/index.html", "word/app.js", "word/style.css", "word/icon.png",
                    "dist/word-manifest.xml", "dist/start-word.command", "dist/start-word.cmd"}
        wrappers = {action + "-word." + suffix for action in ("install", "start", "stop", "status", "uninstall")
                    for suffix in ("command", "cmd")}
        assert set(archive.namelist()) == {"lod-pane-word/" + name for name in expected | wrappers}
        for name in expected - {"START-HERE.txt"}:
            assert archive.read("lod-pane-word/" + name) == (ROOT / name).read_bytes()
        assert archive.getinfo("lod-pane-word/dist/start-word.command").external_attr >> 16 & 0o111
    import hashlib
    for line in (ROOT / "dist/SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ")
        assert hashlib.sha256((ROOT / "dist" / name).read_bytes()).hexdigest() == digest
    print("PASS: live-shape LOD parsing, anchored context, sense separation, stale-write rejection, preferences, offline saved lookup/edit, deletion, HTTP boundaries, and both package formats.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--serve":
        # Browser tests use the same real app/server, replacing only the external dictionary.
        lodpane.fetch_json = fixture_fetch
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        if "--port" not in sys.argv:
            sys.argv += ["--port", os.environ.get("LOD_TEST_PORT", "43127")]
        server.main()
    else:
        run()
