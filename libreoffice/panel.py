"""Reading-first native Writer sidebar. No browser or server.

Actions and choices use native buttons and standard UNO action events. Optional notes and excerpts reveal on demand.
"""
import json
import queue
import traceback
from concurrent.futures import ThreadPoolExecutor
from threading import Timer

import uno
import unohelper
from com.sun.star.awt import XActionListener, XCallback, XKeyListener, XTextListener, XWindowListener
from com.sun.star.awt.Key import ESCAPE, RETURN
from com.sun.star.lang import XComponent
from com.sun.star.ui import XSidebarPanel, XToolPanel, XUIElement, XUIElementFactory
from com.sun.star.view import XSelectionChangeListener

import lodpane

FACTORY = "org.lodpane.PanelFactory"
URL = "private:resource/toolpanel/LODPane/Notebook"
VERSION = "v0.7.0"
WORKERS = ThreadPoolExecutor(max_workers=2)
LANGUAGE_LABELS = {"en": "English", "fr": "Français", "de": "Deutsch"}
DESTINATIONS = ("Study", "Favorites")
ROWS = 10
SENSE_ROWS = 5
GAP = 6          # one spacing unit for the whole column
ROW = 24         # one control height
MAX_WIDTH = 380  # the column never grows past this, however wide the deck is
MUTED = ("pos", "hint", "status", "context_text", "grammar", "version", "page", "example_label", "language_label", "sense_page")


class Panel(unohelper.Base, XToolPanel, XSidebarPanel, XSelectionChangeListener,
            XActionListener, XCallback, XKeyListener, XTextListener, XWindowListener, XComponent):
    def __init__(self, ctx, frame, parent, sidebar=None, theme=None):
        self.ctx = ctx
        self.parent = parent
        self.controller = frame.getController()
        self.sidebar = sidebar
        self.dead = False
        self.visible = True
        self.version = 0
        self.events = queue.SimpleQueue()
        self.callbacks = ctx.ServiceManager.createInstanceWithContext("com.sun.star.awt.AsyncCallback", ctx)
        self.controls = {}
        self.kinds = {}
        self.placed = set()
        self.disabled = set()
        self.settings_open = False
        self.selected = set()
        self.meanings_open = False
        self.sense_page = 0
        self.page = 0
        self.lookup_state = "empty"
        self.entry = None
        self.sense = None
        self.candidates = []
        self.words = []
        self.library_open = False
        self.row_mode = "none"
        self.row_items = []
        self.drafts = {}
        self.selection_text = ""
        self.selection_start = None
        self.selection_end = None
        self.entry_paragraph = ""
        self.replace_open = False
        self.replace_target = None
        self.replacing = False
        self.timer = None
        self.future = None
        self.rendering = False
        self.host_background = None
        self.host_text = None
        self.read_host_theme(theme)
        self.settings = {"theme": "light", "language": "en"}
        self.build_controls()

    # ---------- construction ----------

    def build_controls(self):
        self.Window = self.ctx.ServiceManager.createInstanceWithContext("com.sun.star.awt.UnoControlContainer", self.ctx)
        self.Window.setModel(self.ctx.ServiceManager.createInstanceWithContext("com.sun.star.awt.UnoControlContainerModel", self.ctx))
        toolkit = self.ctx.ServiceManager.createInstanceWithContext("com.sun.star.awt.Toolkit", self.ctx)
        self.Window.createPeer(toolkit, self.parent)
        self.tab_model = self.ctx.ServiceManager.createInstanceWithContext("com.sun.star.awt.TabControllerModel", self.ctx)
        self.tab_controller = self.ctx.ServiceManager.createInstanceWithContext("com.sun.star.awt.TabController", self.ctx)
        self.tab_controller.setModel(self.tab_model)
        self.Window.addTabController(self.tab_controller)
        self._action("home", "Home", center=True)
        self._action("library", "Saved 0", center=True)
        self._action("settings", "Settings", center=True)
        self._field("query", height=ROW, font=9)
        self.assign("query", "HelpText", "Search Luxembourgish. Press Enter to look up.")
        self._action("search", "Look up", center=True)
        self._action("theme", "Use dark theme")
        self._text("version", VERSION)
        self._text("status", "", font=9)
        self._text("word", "", height=30, font=16)
        self.assign("word", "FontName", "Georgia")
        self._text("pos", "", font=9)
        self._text("language_label", "Meaning in", font=8)
        for code, label in LANGUAGE_LABELS.items():
            self._choice("lang_" + code, label, center=True)
        self._action("meanings", "Change meaning")
        for index in range(SENSE_ROWS):
            self._choice("sense%d" % index, "")
        self._action("sense_previous", "Previous", center=True)
        self._text("sense_page", "")
        self._action("sense_next", "Next", center=True)
        self._text("meaning", "", height=34, font=12)
        self._text("grammar", "", font=9)
        self._text("example_label", "Example · Luxembourgish", font=8)
        self._text("example", "", font=10)
        self._action("replace_toggle", "Replace selected text…")
        self._text("replace_preview", "", font=9)
        self._text("replace_hint", "Uses the Luxembourgish headword, not the translation. Check the grammar first. Use Writer's Undo to revert.", font=8)
        self._action("replace_confirm", "Replace selection")
        self._action("note_toggle", "Add a note")
        self._field("note", height=72, font=9, multiline=True)
        self.assign("note", "HelpText", "My note. Saved only when you save the word.")
        self._action("context", "Keep document excerpt")
        self._text("context_text", "", font=9)
        self._field("filter", font=9)
        self.assign("filter", "HelpText", "Find a saved word or note")
        for index in range(ROWS):
            self._action("row%d" % index, "")
        self._action("previous", "Previous", center=True)
        self._text("page", "")
        self._action("next", "Next", center=True)
        for destination in DESTINATIONS:
            self._choice("dest_" + destination.lower(), destination, center=True)
        model = self._create("Button", "Button", "save", 32)
        model.Label = "Save to Study"
        model.FontHeight = 9.0
        model.Tabstop = True
        self.controls["save"].addActionListener(self)
        self.kinds["save"] = "button"
        self._action("forget", "Remove saved word")
        self._text("hint", "Saving vocabulary does not edit the document.")
        self._action("source", "View on LOD")
        self._action("export", "Export vocabulary")
        self.controls["note"].addTextListener(self)
        self.controls["filter"].addTextListener(self)
        self.controls["query"].addKeyListener(self)
        self.controls["filter"].addKeyListener(self)
        self.message("")
        try:
            first_run = not lodpane.has_preferences()
            self.settings = lodpane.preferences()
            if first_run and self.host_background is not None:
                # Match the application on first use; the theme button overrides later.
                self.settings["theme"] = "dark" if sum(self.host_background.to_bytes(3, "big")) < 384 else "light"
            self.words = lodpane.saved_words()
        except Exception as error:
            self.message("Cannot open local vocabulary: " + str(error))
        self.layout(336)
        self.Window.addWindowListener(self)
        self.Window.setVisible(True)
        self.controller.addSelectionChangeListener(self)
        self.selectionChanged(None)

    def _create(self, service_kind, model_kind, name, height):
        model = self.ctx.ServiceManager.createInstanceWithContext("com.sun.star.awt.UnoControl" + model_kind + "Model", self.ctx)
        control = self.ctx.ServiceManager.createInstanceWithContext("com.sun.star.awt.UnoControl" + service_kind, self.ctx)
        control.setModel(model)
        self.Window.addControl(name, control)
        control.setPosSize(16, 0, 304, height, 15)
        self.controls[name] = control
        return model

    def _text(self, name, label, height=18, font=8):
        """Read-only text. Muted or regular color is applied by paint()."""
        model = self._create("FixedText", "FixedText", name, height)
        model.Label = label
        model.MultiLine = True
        model.FontHeight = float(font)
        self.kinds[name] = "text"
        return model

    def _action(self, name, label, height=ROW, font=9, center=False):
        """Use the host's button activation rather than filtering mouse events."""
        model = self._create("Button", "Button", name, height)
        model.Label = label
        model.FontHeight = float(font)
        model.MultiLine = True
        model.Align = 1 if center else 0
        model.Tabstop = True
        self.controls[name].addActionListener(self)
        self.controls[name].addKeyListener(self)
        self.kinds[name] = "action"
        return model

    def _choice(self, name, label, center=False):
        model = self._action(name, label, center=center)
        model.Toggle = True
        self.kinds[name] = "choice"
        return model

    def _field(self, name, height=ROW, font=9, multiline=False):
        """Native text entry. Kept native so typing and selection behave normally."""
        model = self._create("Edit", "Edit", name, height)
        model.FontHeight = float(font)
        model.Tabstop = True
        self.assign_raw(model, "Border", 2)
        if multiline:
            model.MultiLine = True
            model.VScroll = True
            model.MaxTextLen = 2000
        self.kinds[name] = "field"
        return model

    # ---------- defensive model access ----------

    def model(self, name):
        """Control model, or None while the host is (re)building or tearing down."""
        try:
            return self.controls[name].getModel()
        except Exception:
            return None

    def assign(self, name, attribute, value):
        model = self.model(name)
        if model is not None:
            self.assign_raw(model, attribute, value)

    def assign_raw(self, model, attribute, value):
        try:
            if model.getPropertySetInfo().hasPropertyByName(attribute):
                setattr(model, attribute, value)
        except Exception:
            pass

    def label(self, name, text):
        self.assign(name, "Label", text)

    def control_name(self, source):
        return next((name for name, control in self.controls.items() if control == source or control.getPeer() == source), "")

    # ---------- theme and paint ----------

    def read_host_theme(self, theme):
        if theme is None:
            return
        try:
            if theme.getPropertySetInfo().hasPropertyByName("BackgroundColor"):
                self.host_background = theme.getPropertyValue("BackgroundColor")
            if theme.getPropertySetInfo().hasPropertyByName("TextColor"):
                self.host_text = theme.getPropertyValue("TextColor")
        except Exception:
            self.host_background = None
            self.host_text = None

    def palette(self):
        dark = self.settings["theme"] == "dark"
        if dark:
            bg, fg, muted, accent, on_accent, wash, field = 0x111D2E, 0xE4EEF4, 0x9FB6C6, 0x55B5CF, 0x06212B, 0x1B2F47, 0x0B1624
        else:
            bg, fg, muted, accent, on_accent, wash, field = 0xFFFFFF, 0x18323F, 0x5E7685, 0x147F9C, 0xFFFFFF, 0xEEF4F7, 0xFFFFFF
        return {"bg": bg, "fg": fg, "muted": muted, "accent": accent, "on_accent": on_accent, "wash": wash, "field": field}

    def paint(self):
        """Apply the palette to every control, from the current state."""
        p = self.palette()
        container = self.model_container()
        if container is not None:
            self.assign_raw(container, "BackgroundColor", p["bg"])
        for name, kind in self.kinds.items():
            model = self.model(name)
            if model is None:
                continue
            if kind == "text":
                self.assign_raw(model, "BackgroundColor", -1)  # transparent: inherits the surface
                self.assign_raw(model, "TextColor", p["muted"] if name in MUTED else p["fg"])
            elif kind == "field":
                self.assign_raw(model, "BackgroundColor", p["field"])
                self.assign_raw(model, "TextColor", p["fg"])
            elif kind == "choice":
                selected = name in self.selected
                self.assign_raw(model, "BackgroundColor", p["accent"] if selected else p["wash"])
                self.assign_raw(model, "TextColor", p["on_accent"] if selected else p["fg"])
                self.assign_raw(model, "State", 1 if selected else 0)
            else:
                self.assign_raw(model, "BackgroundColor", p["accent"] if kind == "button" else p["wash"])
                self.assign_raw(model, "TextColor", p["on_accent"] if kind == "button" else p["fg"])
            self.assign_raw(model, "Enabled", name not in self.disabled)

    def model_container(self):
        try:
            return self.Window.getModel()
        except Exception:
            return None

    def apply_theme(self):
        self.paint()

    def style_dynamic(self):
        """Paint every choice from the same state as the displayed definition."""
        self.rendering = True
        try:
            language = self.settings["language"]
            self.selected = {"lang_" + language}
            for code, text in LANGUAGE_LABELS.items():
                self.label("lang_" + code, ("✓ " if code == language else "") + text)
            self.label("library", "Back" if self.library_open else "Saved %d" % len(self.words))
            self.label("settings", "Close settings" if self.settings_open else "Settings")
            self.label("theme", "Use light theme" if self.settings["theme"] == "dark" else "Use dark theme")
            self.label("replace_toggle", "Cancel replacement" if self.replace_open else "Replace selected text…")
            if self.replace_target and self.replace_target["original"] != self.replace_target["replacement"]:
                self.disabled.discard("replace_confirm")
            else:
                self.disabled.add("replace_confirm")
            if self.entry:
                value = self.draft()
                for destination in DESTINATIONS:
                    name = "dest_" + destination.lower()
                    active = destination == value["destination"]
                    if active:
                        self.selected.add(name)
                    self.label(name, ("✓ " if active else "") + destination)
                senses = self.entry["senses"]
                current = next(i for i, item in enumerate(senses) if item["id"] == self.sense["id"])
                self.label("meanings", "Hide meanings" if self.meanings_open else "Meaning %d of %d · Change" % (current + 1, len(senses)))
                self.sense_page = min(self.sense_page, (len(senses) - 1) // SENSE_ROWS)
                for slot, item in enumerate(senses[self.sense_page * SENSE_ROWS:(self.sense_page + 1) * SENSE_ROWS]):
                    name = "sense%d" % slot
                    active = item["id"] == self.sense["id"]
                    if active:
                        self.selected.add(name)
                    number = self.sense_page * SENSE_ROWS + slot + 1
                    self.label(name, ("✓ " if active else "") + "%d. %s" % (number, item["translations"].get(language) or "No translation"))
                saved = self.saved_word() or {}
                changed = value["note"] != saved.get("note", "")
                self.label("note_toggle", "My note · unsaved" if changed else "My note" if value["note"] else "Add a note")
                self.label("context", "Remove document excerpt" if value["context"] else "Keep document excerpt")
                self.update_save_button()
        finally:
            self.rendering = False
        self.paint()

    # ---------- state helpers ----------

    def current_key(self):
        return self.entry["id"] + "#" + self.sense["id"]

    def draft(self):
        key = self.current_key()
        if key not in self.drafts:
            saved = self.saved_word() or {}
            self.drafts[key] = {"note": saved.get("note", ""), "context": saved.get("context", ""), "destination": saved.get("destination", "Study"), "note_open": bool(saved.get("note")), "baseUpdated": saved.get("updated")}
        return self.drafts[key]

    def saved_word(self):
        if not self.entry:
            return None
        return next((word for word in self.words if word["key"] == self.current_key()), None)

    def update_save_button(self):
        if not self.entry:
            return
        saved = self.saved_word()
        if saved is None:
            self.label("save", "Save to " + self.draft()["destination"])
            self.label("hint", "Saving vocabulary does not edit the document.")
            self.disabled.discard("save")
            return
        unchanged = all(self.draft()[field] == saved[field] for field in ("note", "context", "destination"))
        self.label("save", "Saved to " + saved["destination"] if unchanged else "Save changes")
        self.label("hint", "Saving vocabulary does not edit the document." if unchanged else "Unsaved changes")
        if unchanged:
            self.disabled.add("save")
        else:
            self.disabled.discard("save")

    def message(self, text):
        self.label("status", text)
        if text or "status" in self.placed:
            self.refresh()

    def mode(self):
        if self.library_open:
            return "library"
        if self.entry:
            return "entry"
        if self.candidates:
            return "candidates"
        return "empty"

    def saved_labels(self, items=None):
        language = self.settings["language"]
        labels = []
        for item in self.words if items is None else items:
            sense = next((value for value in item["entry"]["senses"] if value["id"] == item["senseId"]), None)
            translation = ((sense or {}).get("translations") or {}).get(language) or "no translation"
            labels.append(item["entry"]["word"] + " · " + translation + " · " + item["destination"])
        return labels

    def refresh_saved_list(self):
        self.words = lodpane.saved_words()

    # ---------- layout ----------

    def window_size(self):
        try:
            size = self.Window.getPosSize()
            return max(288, size.Width), max(0, size.Height)
        except Exception:
            return 336, 0

    def refresh(self):
        self.layout(self.window_size()[0])
        self.request_layout()

    def request_layout(self):
        if self.sidebar is not None:
            try:
                self.sidebar.requestLayout()
            except Exception:
                self.sidebar = None

    def layout(self, width):
        """Place controls for the current state. Returns the natural content height."""
        width = max(288, width)
        content = min(MAX_WIDTH, width - 2 * GAP - 16)
        left = max(GAP + 10, (width - content) // 2)
        right = left + content
        self.placed = set()
        self.tab_order = []
        self.style_dynamic()
        y = 12
        self._place("home", left, y, content - 168, ROW)
        self._place("library", right - 160, y, 68, ROW)
        self._place("settings", right - 88, y, 88, ROW)
        y += ROW + GAP
        self._place("query", left, y, content - 58 - GAP, ROW)
        self._place("search", right - 58, y, 58, ROW)
        y += ROW + 16
        if self.settings_open:
            y = self._flow("theme", left, y, content - 70, ROW)
            self._place("version", right - 64, y - ROW - GAP, 64, ROW)
            if self.mode() not in ("entry", "library"):
                y = self.layout_languages(left, content, y)
        model = self.model("status")
        if model is not None and model.Label:
            y = self._flow("status", left, y, content, ROW) + GAP
        if self.mode() == "entry":
            y = self.layout_entry(left, content, y)
        else:
            y = self.layout_list(self.mode(), left, content, y)
        for name, control in self.controls.items():
            if name not in self.placed:
                control.setVisible(False)
        self.tab_model.setControlModels(tuple(self.model(name) for name in self.tab_order if name not in self.disabled and self.model(name) is not None))
        self.tab_controller.activateTabOrder()
        self.min_height = max(360, y + 12)
        return self.min_height

    def _place(self, name, x, y, size, height):
        control = self.controls[name]
        control.setPosSize(x, y, size, height, 15)
        control.setVisible(True)
        self.placed.add(name)
        if self.kinds[name] != "text":
            self.tab_order.append(name)
        return y + height

    def _flow(self, name, left, y, width, minimum=18):
        """Measure wrapped text with the native peer at the actual column width."""
        size = uno.createUnoStruct("com.sun.star.awt.Size", width, minimum)
        try:
            height = max(minimum, self.controls[name].calcAdjustedSize(size).Height + 4)
        except Exception:
            height = minimum
        return self._place(name, left, y, width, height) + GAP

    def layout_languages(self, left, content, y):
        y = self._flow("language_label", left, y, content)
        width = (content - 2 * GAP) // 3
        for index, code in enumerate(LANGUAGE_LABELS):
            self._place("lang_" + code, left + index * (width + GAP), y, width, ROW)
        return y + ROW + GAP

    def layout_list(self, mode, left, content, y):
        if mode == "library":
            query = self.controls["filter"].getText().strip().casefold()
            self.row_items = [item for item in self.words if query in (" ".join((item["entry"]["word"], item["note"], item["destination"], self.saved_labels([item])[0]))).casefold()]
            self.row_mode = "library"
            labels = self.saved_labels(self.row_items)
            title = "Your vocabulary"
            hint = "%d saved meanings" % len(self.words) if labels else "No matches. Try another search." if self.words else "No words saved yet."
        elif mode == "candidates":
            title, hint = "Which word?", "Choose the dictionary entry you meant."
            self.row_mode, self.row_items = "candidates", self.candidates
            labels = [item["word"] + " · " + item["pos"] for item in self.candidates]
        else:
            titles = {"empty": "Select a word.", "loading": "Looking up…", "error": "Lookup unavailable.", "nomatch": "No match found."}
            title = titles[self.lookup_state]
            hint = "Select a Luxembourgish word in your document, or search above."
            if self.lookup_state == "loading":
                hint = "Only the lookup word goes to LOD."
            elif self.lookup_state in ("error", "nomatch"):
                hint = "Try another search, or open Saved."
            self.row_mode, self.row_items = "recent", self.words[:5] if self.lookup_state == "empty" else []
            labels = self.saved_labels(self.row_items)
        self.label("word", title)
        self.label("pos", hint)
        y = self._flow("word", left, y, content, 30)
        y = self._flow("pos", left, y, content) + GAP
        if mode == "library":
            self._place("filter", left, y, content, ROW)
            y = self.layout_languages(left, content, y + ROW + GAP)
        self.page = min(self.page, max(0, (len(labels) - 1) // ROWS))
        for index, text in enumerate(labels[self.page * ROWS:(self.page + 1) * ROWS]):
            name = "row%d" % index
            self.label(name, text)
            y = self._flow(name, left, y, content, ROW)
        if len(labels) > ROWS:
            self.label("page", "%d / %d" % (self.page + 1, (len(labels) + ROWS - 1) // ROWS))
            for name, enabled in (("previous", self.page > 0), ("next", (self.page + 1) * ROWS < len(labels))):
                self.disabled.discard(name) if enabled else self.disabled.add(name)
            self._place("previous", left, y, 72, ROW)
            self._place("page", left + 80, y, content - 160, ROW)
            self._place("next", left + content - 72, y, 72, ROW)
            y += ROW + GAP
        if mode == "library":
            y = self._flow("export", left, y + GAP, content, ROW)
        self.paint()
        return y

    def layout_entry(self, left, content, y):
        entry, sense, value = self.entry, self.sense, self.draft()
        self.label("word", entry["word"])
        self.label("pos", entry["pos"])
        y = self._flow("word", left, y, content, 32)
        y = self._flow("pos", left, y, content, ROW)
        y = self.layout_languages(left, content, y + GAP)
        self.label("meaning", sense["translations"].get(self.settings["language"]) or "No translation. Try another language or meaning.")
        y = self._flow("meaning", left, y, content, 28)
        if sense.get("grammar"):
            self.label("grammar", sense["grammar"])
            y = self._flow("grammar", left, y, content)
        if sense.get("example"):
            y = self._flow("example_label", left, y + GAP, content)
            self.label("example", sense["example"])
            y = self._flow("example", left, y, content, ROW)
        if len(entry["senses"]) > 1:
            y = self._flow("meanings", left, y + GAP, content, ROW)
            if self.meanings_open:
                start = self.sense_page * SENSE_ROWS
                for slot in range(min(SENSE_ROWS, len(entry["senses"]) - start)):
                    y = self._flow("sense%d" % slot, left, y, content, ROW)
                if len(entry["senses"]) > SENSE_ROWS:
                    self.label("sense_page", "%d / %d" % (self.sense_page + 1, (len(entry["senses"]) + SENSE_ROWS - 1) // SENSE_ROWS))
                    for name, enabled in (("sense_previous", self.sense_page > 0), ("sense_next", start + SENSE_ROWS < len(entry["senses"]))):
                        self.disabled.discard(name) if enabled else self.disabled.add(name)
                    self._place("sense_previous", left, y, 72, ROW)
                    self._place("sense_page", left + 80, y, content - 160, ROW)
                    self._place("sense_next", left + content - 72, y, 72, ROW)
                    y += ROW + GAP
                self.paint()
        y = self._flow("replace_toggle", left, y + GAP, content, ROW)
        if self.replace_open:
            y = self._flow("replace_preview", left, y, content, ROW)
            y = self._flow("replace_hint", left, y, content)
            y = self._flow("replace_confirm", left, y, content, ROW)
        y = self._flow("note_toggle", left, y + GAP, content, ROW)
        self.rendering = True
        try:
            self.controls["note"].setText(value["note"])
        finally:
            self.rendering = False
        if value["note_open"] or value["note"]:
            self._place("note", left, y, content, 72)
            y += 72 + GAP
        y = self._flow("context", left, y, content, ROW)
        if value["context"]:
            self.label("context_text", value["context"])
            y = self._flow("context_text", left, y, content, ROW)
        y = self._flow("source", left, y + GAP, content, ROW)
        y += GAP
        half = (content - GAP) // 2
        for index, destination in enumerate(DESTINATIONS):
            self._place("dest_" + destination.lower(), left + index * (half + GAP), y, half, ROW)
        y += ROW + GAP
        self._place("save", left, y, content, 32)
        y += 32 + GAP
        self.label("hint", "Unsaved changes" if self.saved_word() and "save" not in self.disabled else "Saving vocabulary does not edit the document.")
        y = self._flow("hint", left, y, content)
        if self.saved_word() is not None:
            y = self._flow("forget", left, y, content, ROW)
        return y

    # ---------- display and lookup ----------

    def display_entry(self, entry, sense_id=None):
        self.replace_open = False
        self.replace_target = None
        self.entry = entry
        self.sense = next((item for item in entry["senses"] if item["id"] == sense_id), entry["senses"][0])
        self.candidates = []
        self.library_open = False
        self.meanings_open = False
        self.sense_page = next(i for i, item in enumerate(entry["senses"]) if item["id"] == self.sense["id"]) // SENSE_ROWS
        self.lookup_state = "empty"
        self.message("")
        self.refresh()

    def submit(self, function, *args):
        self.version += 1
        version = self.version
        if self.timer:
            self.timer.cancel()
        if self.future:
            self.future.cancel()
        self.entry = None
        self.candidates = []
        self.replace_open = False
        self.replace_target = None
        self.library_open = False
        self.page = 0
        self.lookup_state = "loading"
        self.message("")
        self.refresh()

        def completed(result):
            try:
                value = result.result()
            except Exception as error:
                value = error
            if not self.dead:
                self.events.put((version, value))
                self.callbacks.addCallback(self, None)

        def start():
            if self.dead or version != self.version:
                return
            self.future = WORKERS.submit(function, *args)
            self.future.add_done_callback(completed)

        self.timer = Timer(0.25, start)
        self.timer.daemon = True
        self.timer.start()

    def notify(self, data):
        while not self.events.empty():
            version, value = self.events.get()
            if self.dead or version != self.version:
                continue
            if isinstance(value, Exception):
                self.lookup_state = "error"
                self.message(str(value))
                self.refresh()
                continue
            if value.get("entry"):
                self.display_entry(value["entry"])
                if value.get("offline"):
                    self.message("LOD is offline. Showing your saved copy.")
            else:
                self.candidates = value.get("candidates", [])
                self.lookup_state = "nomatch"
                self.message("" if self.candidates else "Check the spelling or try the dictionary headword.")
                self.refresh()

    def selectionChanged(self, event):
        if self.dead or not self.visible or self.replacing:
            return
        try:
            selection = self.controller.getSelection()
            if not selection or not selection.supportsService("com.sun.star.text.TextRanges") or selection.getCount() != 1:
                return
            selected = selection.getByIndex(0)
            text = selected.getString()
            if not text.strip():
                return
            same_range = self.selection_range_matches(selected)
            self.selection_start = selected.getStart()
            self.selection_end = selected.getEnd()
            word = lodpane.normalize_word(text)
            cursor = selected.getText().createTextCursorByRange(selected.getStart())
            cursor.gotoStartOfParagraph(False)
            cursor.gotoEndOfParagraph(True)
            self.entry_paragraph = lodpane.context_excerpt(cursor.getString(), word)
            self.selection_text = text
            if same_range:
                return
            if self.replace_open:
                self.message("Selection changed. Reopen the replacement preview.")
                return
            self.submit(lodpane.lookup, word)
        except ValueError as error:
            self.version += 1
            self.entry_paragraph = ""
            self.message(str(error))
        except Exception:
            self.message("Use the search field for this selection.")

    def selection_range_matches(self, selected):
        if self.selection_start is None or self.selection_end is None:
            return False
        try:
            text = selected.getText()
            return (text.compareRegionStarts(selected.getStart(), self.selection_start) == 0
                    and text.compareRegionEnds(selected.getEnd(), self.selection_end) == 0)
        except Exception:
            return False

    # ---------- events ----------

    def keyPressed(self, event):
        name = self.control_name(event.Source)
        if event.KeyCode == RETURN and name == "query":
            self.handle("search")
        elif event.KeyCode == ESCAPE and self.settings_open:
            self.settings_open = False
            self.refresh()
            self.controls["settings"].setFocus()

    def keyReleased(self, event):
        pass

    def textChanged(self, event):
        if self.rendering or self.dead:
            return
        if self.control_name(event.Source) == "filter":
            self.page = 0
            self.refresh()
        elif self.entry:
            self.draft()["note"] = self.controls["note"].getText()
            self.draft()["note_open"] = True
            self.style_dynamic()

    def handle(self, name):
        """Every native button action lands here, independent of mouse details."""
        if self.dead or name in self.disabled:
            return
        try:
            if name == "home":
                self.go_home()
            elif name == "replace_toggle" and self.entry:
                if self.replace_open:
                    self.replace_open = False
                    self.replace_target = None
                    self.refresh()
                else:
                    self.prepare_replacement()
            elif name == "replace_confirm" and self.entry:
                self.replace_selection()
            elif name.startswith("row"):
                self.open_row(int(name[3:]))
            elif name.startswith("lang_"):
                language = name[5:]
                lodpane.preferences({"language": language})
                self.settings["language"] = language
                self.refresh()
            elif name.startswith("dest_") and self.entry:
                self.draft()["destination"] = name[5:].capitalize()
                self.refresh()
            elif name == "meanings" and self.entry:
                self.meanings_open = not self.meanings_open
                self.refresh()
            elif name in ("sense_previous", "sense_next"):
                self.sense_page += -1 if name == "sense_previous" else 1
                self.refresh()
            elif name.startswith("sense") and name[5:].isdigit() and self.entry and self.meanings_open:
                index = self.sense_page * SENSE_ROWS + int(name[5:])
                if index < len(self.entry["senses"]):
                    self.sense = self.entry["senses"][index]
                    self.meanings_open = False
                    self.refresh()
            elif name in ("previous", "next"):
                self.page += -1 if name == "previous" else 1
                self.refresh()
            elif name == "settings":
                self.settings_open = not self.settings_open
                self.refresh()
            elif name == "note_toggle" and self.entry:
                self.draft()["note_open"] = not self.draft()["note_open"]
                self.refresh()
                if self.controls["note"].isVisible():
                    self.controls["note"].setFocus()
            elif name == "context" and self.entry:
                self.toggle_context()
            elif name == "theme":
                self.settings["theme"] = "dark" if self.settings["theme"] == "light" else "light"
                lodpane.preferences({"theme": self.settings["theme"]})
                self.refresh()
            elif name == "search":
                word = lodpane.normalize_word(self.controls["query"].getText())
                self.entry_paragraph = ""
                self.submit(lodpane.lookup, word)
            elif name == "library":
                self.library_open = not self.library_open
                if self.library_open:
                    self.replace_open = False
                    self.replace_target = None
                    self.version += 1
                    if self.timer:
                        self.timer.cancel()
                    if self.future:
                        self.future.cancel()
                    self.lookup_state = "empty"
                    self.page = 0
                    self.controls["filter"].setText("")
                    self.refresh_saved_list()
                self.message("")
                self.refresh()
            elif name == "save" and self.entry:
                value = self.draft()
                saved = lodpane.save_word({"entryId": self.entry["id"], "senseId": self.sense["id"], **{key: value[key] for key in ("note", "context", "destination", "baseUpdated")}})
                self.draft()["baseUpdated"] = saved["updated"]
                self.refresh_saved_list()
                self.message(self.entry["word"] + " saved to " + self.draft()["destination"] + ".")
                self.refresh()
            elif name == "forget" and self.entry:
                self.forget_current()
            elif name == "source" and self.entry:
                shell = self.ctx.ServiceManager.createInstanceWithContext("com.sun.star.system.SystemShellExecute", self.ctx)
                shell.execute(self.entry["url"], "", 0)
            elif name == "export":
                self.export_vocabulary()
        except Exception as error:
            prefix = "Could not replace selection. " if name.startswith("replace_") else "Could not complete this action. Your note is still here. "
            self.message(prefix + str(error))
            if name.startswith("replace_"):
                self.refresh()

    def go_home(self):
        self.version += 1
        if self.timer:
            self.timer.cancel()
        if self.future:
            self.future.cancel()
        self.entry = self.sense = None
        self.candidates = []
        self.library_open = self.settings_open = self.meanings_open = False
        self.replace_open = False
        self.replace_target = None
        self.lookup_state = "empty"
        self.entry_paragraph = ""
        self.page = self.sense_page = 0
        self.controls["query"].setText("")
        self.label("status", "")
        self.refresh()
        self.controls["query"].setFocus()

    def document_selection(self):
        doc = self.controller.getModel()
        if doc.isReadonly():
            raise ValueError("This document is read-only.")
        selection = self.controller.getSelection()
        if not selection or not selection.supportsService("com.sun.star.text.TextRanges") or selection.getCount() != 1:
            raise ValueError("Select one word in the document and reopen the preview.")
        selected = selection.getByIndex(0)
        original = selected.getString()
        lodpane.normalize_word(original)
        if "\n" in original or "\r" in original:
            raise ValueError("Select one word without paragraph breaks and reopen the preview.")
        return doc, selected

    def prepare_replacement(self):
        doc, selected = self.document_selection()
        original = selected.getString()
        text = selected.getText()
        cursor = text.createTextCursorByRange(selected.getStart())
        cursor.gotoRange(selected.getEnd(), True)
        replacement = original[:len(original) - len(original.lstrip())] + self.entry["word"] + original[len(original.rstrip()):]
        self.replace_target = {"doc": doc, "range": cursor, "original": original, "replacement": replacement}
        self.replace_open = True
        self.label("replace_preview", "Selected: %r\nReplace with: %r" % (original, replacement))
        if original == replacement:
            self.label("replace_preview", "The selection already matches this headword.")
        self.refresh()

    def replace_selection(self):
        target = self.replace_target
        if target is None:
            return
        # Invalidate the preview even if validation or the host edit fails.
        self.replace_target = None
        doc, current = self.document_selection()
        captured = target["range"]
        text = captured.getText()
        if (doc != target["doc"] or current.getText() != text
                or current.getString() != target["original"] or captured.getString() != target["original"]
                or text.compareRegionStarts(current.getStart(), captured.getStart()) != 0
                or text.compareRegionEnds(current.getEnd(), captured.getEnd()) != 0):
            raise ValueError("The selection changed. Nothing was replaced. Reopen the preview.")
        self.version += 1
        if self.timer:
            self.timer.cancel()
        self.replacing = True
        try:
            undo = doc.getUndoManager()
            undo.enterUndoContext("Replace with LOD headword")
            try:
                text.insertString(captured, target["replacement"], True)
                self.controller.select(captured)
            finally:
                undo.leaveUndoContext()
            self.selection_text = captured.getString()
            self.entry_paragraph = ""
        finally:
            self.replacing = False
        self.replace_open = False
        self.message("Selection replaced. Use Writer's Undo to revert.")
        self.refresh()

    def toggle_context(self):
        if self.draft()["context"]:
            self.draft()["context"] = ""
        elif self.entry_paragraph:
            self.draft()["context"] = self.entry_paragraph
        else:
            self.message("Select the word inside its sentence to keep that excerpt.")
            return
        self.refresh()

    def open_row(self, index):
        index += self.page * ROWS
        if index >= len(self.row_items):
            return
        if self.row_mode == "candidates":
            identifier = self.row_items[index]["id"]
            self.submit(lambda value: {"entry": lodpane.entry(value)}, identifier)
        elif self.row_mode in ("library", "recent"):
            item = self.row_items[index]
            self.entry_paragraph = ""
            self.display_entry(item["entry"], item["senseId"])

    def forget_current(self):
        saved = self.saved_word()
        if saved is None:
            return
        peer = self.Window.getPeer()
        box = peer.getToolkit().createMessageBox(peer, uno.Enum("com.sun.star.awt.MessageBoxType", "QUERYBOX"), 3,
                                                 "Remove word?", "Remove " + saved["entry"]["word"] + " and its note from your vocabulary?")
        if box.execute() == 2:
            lodpane.delete_word(saved["key"], saved["updated"])
            if saved["key"] in self.drafts:
                self.drafts[saved["key"]]["baseUpdated"] = None
            self.refresh_saved_list()
            self.message(saved["entry"]["word"] + " removed.")
            self.refresh()

    def export_vocabulary(self):
        picker = self.ctx.ServiceManager.createInstanceWithContext("com.sun.star.ui.dialogs.FilePicker", self.ctx)
        picker.initialize((uno.Any("short", 1),))
        picker.appendFilter("JSON vocabulary", "*.json")
        picker.setDefaultName("lod-pane-vocabulary.json")
        if picker.execute() == 1:
            path = uno.fileUrlToSystemPath(picker.getFiles()[0])
            with open(path, "w", encoding="utf-8") as output:
                json.dump({"version": 1, "words": lodpane.saved_words()}, output, ensure_ascii=False, indent=2)
            self.message("Vocabulary exported.")

    def actionPerformed(self, event):
        """Compatibility entry point: resolves the control, then runs the same handler."""
        self.handle(self.control_name(event.Source))

    # ---------- panel contract ----------

    def createAccessible(self, parent):
        return self.Window.getAccessibleContext()

    def getHeightForWidth(self, width):
        height = self.layout(width)
        return uno.createUnoStruct("com.sun.star.ui.LayoutSize", height, -1, height)

    def getMinimalWidth(self):
        return 288

    def windowResized(self, event):
        if not self.dead:
            self.layout(event.Width)

    def windowMoved(self, event):
        pass

    def windowShown(self, event):
        self.visible = True
        self.selection_text = ""
        self.selectionChanged(None)

    def windowHidden(self, event):
        self.visible = False
        self.replace_open = False
        self.replace_target = None
        self.version += 1
        if self.timer:
            self.timer.cancel()
        if self.future:
            self.future.cancel()

    def disposing(self, event):
        self.close()

    def close(self):
        self.replace_target = None
        self.replace_open = False
        self.selection_start = None
        self.selection_end = None
        if not self.dead:
            self.dead = True
            self.version += 1
            if self.timer:
                self.timer.cancel()
            if self.future:
                self.future.cancel()
            try:
                self.controller.removeSelectionChangeListener(self)
            except Exception:
                pass  # The controller or document may already be gone.
        self.sidebar = None


class Element(unohelper.Base, XUIElement, XComponent):
    def __init__(self, ctx, frame, parent, url, sidebar=None, theme=None):
        self.Frame, self.ResourceURL, self.Type = frame, url, 7
        self.panel = Panel(ctx, frame, parent, sidebar, theme)

    def getRealInterface(self):
        return self.panel

    def dispose(self):
        # Teardown must never throw: the host may dispose the panel at any time.
        panel, self.panel = self.panel, None
        if panel is not None:
            try:
                panel.close()
            except Exception:
                pass
            try:
                panel.Window.dispose()
            except Exception:
                pass

    def addEventListener(self, listener):
        pass

    def removeEventListener(self, listener):
        pass


class Factory(unohelper.Base, XUIElementFactory):
    def __init__(self, ctx):
        self.ctx = ctx

    def createUIElement(self, url, properties):
        args = {prop.Name: prop.Value for prop in properties}
        if url != URL:
            raise ValueError("Unknown LOD pane resource.")
        try:
            return Element(self.ctx, args["Frame"], args["ParentWindow"], url, args.get("Sidebar"), args.get("Theme"))
        except Exception:
            # LibreOffice hides construction failures behind a blank sidebar.
            try:
                directory = lodpane.data_directory()
                directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                (directory / "panel-error.log").write_text(traceback.format_exc(), encoding="utf-8")
            except OSError:
                pass
            raise


g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(Factory, FACTORY, (FACTORY,))
