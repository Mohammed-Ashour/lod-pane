'use strict';
const $ = selector => document.querySelector(selector);
let words = [], settings = {theme: 'light', language: 'en'};
let currentEntry = null, currentSense = null, generation = 0, pending = null;
let selectionText = '', entrySelection = '', contextProvider = null, busy = false, libraryOpen = false, lookupPending = false;
let replacementProvider = null, replacementTarget = null, replacementVersion = 0, replacing = false;
const drafts = new Map();
let undoAction = null, toastTimer, selectionTimer;

async function api(path, data, signal) {
  const response = await fetch('/api/' + path, {
    method: data === undefined ? 'GET' : 'POST',
    headers: {'X-LOD-Pane': '1', ...(data === undefined ? {} : {'Content-Type': 'application/json'})},
    body: data === undefined ? undefined : JSON.stringify(data), signal
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Could not complete this request. Try again.');
  return result;
}
function status(message = '', error = false) {
  $('#status').textContent = message;
  $('#status').dataset.error = String(error);
}
function key() { return currentEntry.id + '#' + currentSense.id; }
function excerptAround(text, word, limit = 1000) {
  const value = text.trim();
  if (value.length <= limit) return value;
  const needle = word.trim();
  const index = value.toLowerCase().indexOf(needle.toLowerCase());
  if (index < 0) return value.slice(0, limit).trimEnd();
  const roomBefore = Math.max(0, limit - needle.length) >> 1;
  const start = Math.max(0, Math.min(index - roomBefore, value.length - limit));
  return value.slice(start, start + limit).trim();
}
function draft() {
  if (!drafts.has(key())) {
    const saved = words.find(item => item.key === key());
    drafts.set(key(), {note: saved?.note || '', context: saved?.context || '', destination: saved?.destination || 'Study', noteOpen: !!saved?.note, contextOpen: !!saved?.context, baseUpdated: saved?.updated || null});
  }
  return drafts.get(key());
}
function savePayload(entry = currentEntry, sense = currentSense, value = draft()) {
  return {entryId: entry.id, senseId: sense.id, note: value.note, context: value.context, destination: value.destination, baseUpdated: value.baseUpdated};
}
function updateSave() {
  $('#count').textContent = String(words.length);
  if (!currentEntry || !currentSense) return;
  const saved = words.find(item => item.key === key()), value = draft();
  const unchanged = saved && ['note', 'context', 'destination'].every(field => value[field] === saved[field]);
  $('#save').disabled = busy || unchanged;
  $('#save').textContent = busy ? 'Saving…' : unchanged ? 'Saved to ' + saved.destination : saved ? 'Save changes' : 'Save to ' + value.destination;
  const noteChanged = value.note !== (saved?.note || '');
  $('#note-label').textContent = value.note ? 'My note' : 'Add a note';
  $('#note-state').textContent = noteChanged ? 'Unsaved' : value.note ? 'Saved' : '';
  $('#context-state').textContent = value.context ? 'Included' : '';
  $('#save-status').textContent = saved && !unchanged ? 'Unsaved changes' : 'Saving vocabulary does not edit your document.';
  $('#capture').hidden = libraryOpen || lookupPending;
}
function applyTheme() {
  document.documentElement.dataset.theme = settings.theme;
  const next = settings.theme === 'light' ? 'Dark' : 'Light';
  $('#theme').textContent = 'Use ' + next.toLowerCase() + ' theme';
  $('#theme').setAttribute('aria-label', 'Use ' + next.toLowerCase() + ' theme');
}
function renderSense() {
  const value = draft(), translation = currentSense.translations[settings.language];
  $('#meaning').textContent = translation || '';
  $('#meaning').lang = settings.language;
  $('#missing-translation').hidden = !!translation;
  $('#grammar').textContent = currentSense.grammar || '';
  $('#grammar-block').hidden = !currentSense.grammar;
  $('#example').textContent = currentSense.example;
  $('#example-block').hidden = !currentSense.example;
  $('#replace-details').hidden = !replacementProvider;
  $('#note').value = value.note;
  $('#note-details').open = value.noteOpen;
  $('#context-details').open = value.contextOpen;
  $('#destination').value = value.destination;
  $('#keep-context').checked = !!value.context;
  $('#keep-context').disabled = (!contextProvider || !entrySelection) && !value.context;
  $('#keep-context').title = contextProvider && entrySelection ? '' : 'Select a word inside Word to capture nearby text.';
  $('#context-hint').textContent = (contextProvider && entrySelection) || value.context ? 'Optional. Only the lookup word goes to LOD.' : 'Select this word in your document to attach its paragraph.';
  $('#context').textContent = value.context;
  $('#context').hidden = !value.context;
  updateSave();
}
function showEntry(entry, senseId) {
  const changed = entry.id !== currentEntry?.id || (senseId && senseId !== currentSense?.id);
  if (changed) closeReplacement();
  currentEntry = entry;
  currentSense = entry.senses.find(sense => sense.id === senseId) || entry.senses[0];
  libraryOpen = false;
  $('#library').setAttribute('aria-pressed', 'false');
  $('#lookup-view').hidden = false; $('#saved-view').hidden = true;
  $('#empty').hidden = true; $('#candidates').hidden = true; $('#entry').hidden = false;
  $('#headword').textContent = entry.word; $('#pos').textContent = entry.pos;
  $('#source').href = entry.url;
  $('#sense').replaceChildren(...entry.senses.map((sense, index) => {
    const option = document.createElement('option'); option.value = sense.id;
    option.textContent = (index + 1) + '. ' + (sense.translations[settings.language] || 'Meaning ' + (index + 1));
    return option;
  }));
  $('#sense-row').hidden = entry.senses.length < 2;
  $('#sense').value = currentSense.id;
  renderSense();
  if (changed) $('#lookup-view').scrollTop = 0;
}
function emptyState(title, message) {
  $('#empty h1').textContent = title;
  $('#empty p').textContent = message;
  $('#empty').hidden = false;
}
async function lookup(value, entryId = null, fromDocument = false) {
  const query = value.trim(); if (!query) return;
  closeReplacement();
  if (!entryId && (query.length > 80 || /\s/.test(query))) {
    generation++; pending?.abort(); lookupPending = false; entrySelection = '';
    libraryOpen = false; $('#lookup-view').hidden = false; $('#saved-view').hidden = true;
    $('#library').setAttribute('aria-pressed', 'false');
    $('#lookup-view').setAttribute('aria-busy', 'false');
    $('#entry').hidden = true; $('#candidates').hidden = true; $('#capture').hidden = true; $('#empty').hidden = false;
    emptyState('One word at a time.', 'Select one Luxembourgish word, or search for its dictionary headword.');
    status('Select one word, or type it in the search field.', true);
    return;
  }
  entrySelection = fromDocument ? selectionText : entryId ? entrySelection : '';
  lookupPending = true;
  const version = ++generation; pending?.abort(); pending = new AbortController();
  const controller = pending;
  const timeout = setTimeout(() => controller.abort(), 18000);
  libraryOpen = false;
  $('#library').setAttribute('aria-pressed', 'false');
  $('#lookup-view').hidden = false; $('#saved-view').hidden = true;
  $('#lookup-view').setAttribute('aria-busy', 'true');
  $('#capture').hidden = true; $('#entry').hidden = true; $('#candidates').hidden = true;
  $('#empty').hidden = true; status('Looking up ' + query + '…');
  try {
    const result = await api(entryId ? 'entry?id=' + encodeURIComponent(entryId) : 'lookup?word=' + encodeURIComponent(query), undefined, controller.signal);
    if (version !== generation) return;
    lookupPending = false;
    if (result.entry) {
      showEntry(result.entry);
      status(result.offline ? 'LOD is offline. Showing the copy in your saved vocabulary.' : '');
    } else if (result.candidates?.length) {
      currentEntry = null; currentSense = null;
      $('#candidate-list').replaceChildren(...result.candidates.map(candidate => {
        const button = document.createElement('button'); button.className = 'candidate';
        const title = document.createElement('strong'); title.lang = 'lb'; title.textContent = candidate.word;
        const pos = document.createElement('span'); pos.textContent = candidate.pos;
        button.append(title, pos); button.addEventListener('click', () => lookup(candidate.word, candidate.id));
        return button;
      }));
      $('#candidates').hidden = false; status('');
    } else {
      currentEntry = null; currentSense = null;
      emptyState('No match found.', 'Check the spelling or try the dictionary headword.');
      status('No LOD match for "' + query + '".');
    }
  } catch (error) {
    if (version !== generation) return;
    lookupPending = false;
    emptyState('Could not look up this word.', 'Try searching again, or open Saved to read your vocabulary.');
    status(error.name === 'AbortError' ? 'Lookup took too long. Try again using the search field.' : error.message, true);
  } finally {
    clearTimeout(timeout);
    if (version === generation) $('#lookup-view').setAttribute('aria-busy', 'false');
  }
}
function toast(message, undo = null) {
  clearTimeout(toastTimer); undoAction = undo;
  $('#toast-text').textContent = message; $('#undo').hidden = !undo;
  $('#toast').hidden = false;
  toastTimer = setTimeout(() => { $('#toast').hidden = true; undoAction = null; }, 10000);
}
function payloadFromSaved(item, baseUpdated = null) {
  return {entryId: item.entry.id, senseId: item.senseId, note: item.note, context: item.context, destination: item.destination, baseUpdated};
}
async function save() {
  if (!currentEntry || busy) return;
  const selectedKey = key(), payload = savePayload(), previous = words.find(item => item.key === selectedKey);
  busy = true; updateSave(); status('');
  try {
    const result = await api('save', payload);
    words = [result, ...words.filter(item => item.key !== result.key)];
    if (drafts.has(result.key)) drafts.get(result.key).baseUpdated = result.updated;
    toast(result.entry.word + ' saved to ' + result.destination + '.', async () => {
      if (previous) await api('save', payloadFromSaved(previous, result.updated));
      else await api('delete', {key: result.key, baseUpdated: result.updated});
      words = await api('words');
      const restored = words.find(item => item.key === result.key);
      if (drafts.has(result.key)) drafts.get(result.key).baseUpdated = restored?.updated || null;
      if (libraryOpen) renderLibrary(); else updateSave();
      toast('Save undone.');
    });
  } catch (error) { status('Not saved. ' + error.message, true); }
  finally { busy = false; updateSave(); }
}
function renderLibrary() {
  closeReplacement();
  libraryOpen = true;
  $('#library').setAttribute('aria-pressed', 'true');
  $('#lookup-view').setAttribute('aria-busy', 'false');
  $('#lookup-view').hidden = true; $('#saved-view').hidden = false; $('#capture').hidden = true;
  $('#saved-list').replaceChildren();
  const query = $('#saved-query').value.trim().toLocaleLowerCase();
  const filtered = words.filter(item => {
    const sense = item.entry.senses.find(value => value.id === item.senseId);
    return [item.entry.word, item.note, item.destination, sense?.translations[settings.language] || ''].some(text => text.toLocaleLowerCase().includes(query));
  });
  $('#saved-summary').textContent = query ? filtered.length + ' of ' + words.length + ' saved meanings' : words.length + ' saved ' + (words.length === 1 ? 'meaning' : 'meanings');
  if (!filtered.length) {
    const empty = document.createElement('p'); empty.className = 'hint';
    empty.textContent = words.length ? 'No saved words match. Try another search.' : 'No words saved yet. Look up a word, then save it here.';
    $('#saved-list').append(empty);
  }
  for (const item of filtered) {
    const section = document.createElement('article'); section.className = 'saved-item';
    const button = document.createElement('button'); button.className = 'open-word'; button.textContent = item.entry.word; button.lang = 'lb';
    button.addEventListener('click', () => { generation++; pending?.abort(); lookupPending = false; entrySelection = ''; showEntry(item.entry, item.senseId); status(''); $('#headword').focus(); });
    const gloss = document.createElement('p');
    const sense = item.entry.senses.find(value => value.id === item.senseId);
    gloss.textContent = (sense?.translations[settings.language] || 'No translation') + ' · ' + item.destination;
    section.append(button, gloss);
    for (const text of [item.note && 'My note: ' + item.note, item.context]) {
      if (text) { const p = document.createElement('p'); p.textContent = text; section.append(p); }
    }
    const remove = document.createElement('button'); remove.className = 'remove'; remove.textContent = 'Remove';
    remove.setAttribute('aria-label', 'Remove ' + item.entry.word);
    remove.addEventListener('click', async () => {
      remove.disabled = true;
      try {
        await api('delete', {key: item.key, baseUpdated: item.updated}); words = words.filter(value => value.key !== item.key);
        if (drafts.has(item.key)) drafts.get(item.key).baseUpdated = null;
        renderLibrary(); $('#count').textContent = String(words.length);
        toast(item.entry.word + ' removed.', async () => {
          const restored = await api('save', payloadFromSaved(item));
          words = await api('words');
          if (drafts.has(item.key)) drafts.get(item.key).baseUpdated = restored.updated;
          if (libraryOpen) renderLibrary(); updateSave(); toast('Word restored.');
        });
      } catch (error) { status(error.message, true); remove.disabled = false; }
    });
    section.append(remove); $('#saved-list').append(section);
  }
  $('#count').textContent = String(words.length);
}
function back() {
  libraryOpen = false; $('#saved-view').hidden = true; $('#lookup-view').hidden = false;
  $('#library').setAttribute('aria-pressed', 'false');
  if (currentEntry) { showEntry(currentEntry, currentSense.id); $('#headword').focus(); }
  else { emptyState('Select a word.', 'Select a Luxembourgish word in your document, or search above.'); $('#query').focus(); }
}
function goHome() {
  if (replacing) return;
  generation++; pending?.abort(); clearTimeout(selectionTimer);
  closeReplacement();
  currentEntry = null; currentSense = null; entrySelection = '';
  selectionText = '';
  libraryOpen = false; lookupPending = false;
  $('#settings').open = false;
  $('#query').value = ''; $('#saved-query').value = '';
  $('#library').setAttribute('aria-pressed', 'false');
  $('#saved-view').hidden = true; $('#lookup-view').hidden = false;
  $('#entry').hidden = true; $('#candidates').hidden = true; $('#capture').hidden = true;
  $('#lookup-view').setAttribute('aria-busy', 'false'); $('#lookup-view').scrollTop = 0;
  emptyState('Select a word.', 'Select a Luxembourgish word in your document, or search above.');
  status(''); $('#query').focus();
}
function validateReplacementSelection(text) {
  if (!text.trim() || text.trim().length > 80 || /\s/.test(text.trim()) || /[\r\n]/.test(text)) throw new Error('Select one word in your document, then reopen this preview.');
}
function closeReplacement(collapse = true) {
  replacementVersion++;
  const target = replacementTarget; replacementTarget = null;
  if (target && !replacing) void replacementProvider.release(target);
  $('#replace-confirm').disabled = true;
  $('#replace-preview').hidden = true;
  $('#replace-status').textContent = '';
  if (collapse) $('#replace-details').open = false;
}
async function prepareReplacement() {
  closeReplacement(false);
  const version = replacementVersion;
  $('#replace-status').textContent = 'Reading the document selection…';
  if (!replacementProvider || !currentEntry) return;
  try {
    const target = await replacementProvider.capture();
    if (version !== replacementVersion || !currentEntry || libraryOpen || !$('#replace-details').open) { await replacementProvider.release(target); return; }
    target.replacement = target.text.match(/^\s*/)[0] + currentEntry.word + target.text.match(/\s*$/)[0];
    replacementTarget = target;
    $('#replace-before').textContent = target.text;
    $('#replace-after').textContent = target.replacement;
    $('#replace-preview').hidden = false;
    const unchanged = target.text === target.replacement;
    $('#replace-confirm').disabled = unchanged;
    $('#replace-status').textContent = unchanged ? 'The selection already matches this headword.' : 'Only this selection will change. You can use Word’s Undo afterward.';
    $('#replace-confirm').scrollIntoView({block: 'nearest'});
  } catch (error) { if (version === replacementVersion) $('#replace-status').textContent = error.message; }
}
async function replaceSelection() {
  const target = replacementTarget, version = replacementVersion;
  if (!target || replacing) return;
  replacing = true;
  $('#replace-confirm').disabled = true; $('#home').disabled = true; $('#library').disabled = true;
  try {
    await replacementProvider.replace(target, () => replacementTarget === target && replacementVersion === version);
    selectionText = target.replacement; entrySelection = '';
    closeReplacement();
    if (currentEntry && !libraryOpen) renderSense();
    status('Selection replaced. Use Word’s Undo to revert.');
  } catch (error) {
    closeReplacement(false);
    $('#replace-status').textContent = error.message + ' Reopen the preview to try again.';
  } finally {
    await replacementProvider.release(target);
    replacing = false; $('#home').disabled = false; $('#library').disabled = false;
  }
}
function readSelectedText() {
  return new Promise((resolve, reject) => Office.context.document.getSelectedDataAsync(Office.CoercionType.Text, result => {
    if (result.status === Office.AsyncResultStatus.Succeeded) resolve(result.value || '');
    else reject(new Error('Cannot read the selection. Type the word above instead.'));
  }));
}
async function selectionChanged() {
  if (replacing) return;
  const version = generation;
  try {
    const text = await readSelectedText();
    if (replacing || version !== generation) return;
    if (!text.trim()) return; // Moving focus into the pane must not clear a draft.
    if (text === selectionText) return;
    selectionText = text;
    generation++; pending?.abort();
    clearTimeout(selectionTimer);
    selectionTimer = setTimeout(() => lookup(text, null, true), 250);
  } catch (error) { status(error.message, true); }
}
async function startWord() {
  const version = generation;
  $('#connection').textContent = 'Connecting to Word…';
  try {
    await new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://appsforoffice.microsoft.com/lib/1/hosted/office.js';
      script.onload = resolve; script.onerror = () => reject(new Error('Word connection failed. Check your internet connection, then reopen the pane.'));
      document.head.append(script);
    });
    const info = await Office.onReady();
    if (info.host !== Office.HostType.Word) throw new Error('Open LOD pane from Word to follow document selection. Manual lookup is available here.');
    contextProvider = async () => {
      const expectedSelection = entrySelection;
      return Word.run(async context => {
        const selection = context.document.getSelection();
        const paragraph = selection.paragraphs.getFirst();
        selection.load('text'); paragraph.load('text'); await context.sync();
        if (!expectedSelection.trim() || selection.text.trim() !== expectedSelection.trim()) throw new Error('Select this word in the document again before keeping nearby text.');
        return excerptAround(paragraph.text, expectedSelection);
      });
    };
    replacementProvider = {
      async capture() {
        if (Office.context.document.mode && Office.context.document.mode === Office.DocumentMode?.ReadOnly) throw new Error('This document is read-only.');
        let target;
        try {
          return await Word.run(async context => {
            const range = context.document.getSelection();
            range.load('text'); await context.sync();
            validateReplacementSelection(range.text);
            range.track(); target = {range, text: range.text};
            await context.sync();
            return target;
          });
        } catch (error) { if (target) await this.release(target); throw error; }
      },
      async replace(target, valid) {
        if (Office.context.document.mode && Office.context.document.mode === Office.DocumentMode?.ReadOnly) throw new Error('This document is read-only.');
        await Word.run(target.range, async context => {
          const current = context.document.getSelection();
          current.load('text'); target.range.load('text');
          const location = target.range.compareLocationWith(current);
          await context.sync();
          if (!valid()) throw new Error('Replacement cancelled.');
          if (String(location.value).toLowerCase() !== 'equal' || current.text !== target.text || target.range.text !== target.text) throw new Error('The selection changed. Nothing was replaced.');
          current.insertText(target.replacement, Word.InsertLocation.replace);
          await context.sync();
        });
      },
      async release(target) {
        try { await Word.run(target.range, async context => { target.range.untrack(); await context.sync(); }); }
        catch (_) { /* The host may have closed the document. */ }
      }
    };
    Office.context.document.addHandlerAsync(Office.EventType.DocumentSelectionChanged, selectionChanged, result => {
      $('#connection').textContent = result.status === Office.AsyncResultStatus.Succeeded ? 'Following your Word selection. Editing requires Replace selection.' : 'Automatic selection is unavailable. Use selection or type a word.';
    });
    $('#refresh').hidden = false;
    if (currentEntry) renderSense();
    if (version === generation) await selectionChanged();
  } catch (error) { $('#connection').textContent = error.message; status(error.message, true); }
}
$('#replace-details').addEventListener('toggle', () => {
  if ($('#replace-details').open) void prepareReplacement(); else closeReplacement(false);
});
$('#replace-confirm').addEventListener('click', replaceSelection);
window.addEventListener('pagehide', () => closeReplacement());
$('#search').addEventListener('submit', event => { event.preventDefault(); clearTimeout(selectionTimer); lookup($('#query').value); });
$('#note').addEventListener('input', () => { if (currentEntry) { draft().note = $('#note').value; draft().noteOpen = true; updateSave(); } });
for (const [selector, field] of [['#note-details', 'noteOpen'], ['#context-details', 'contextOpen']]) {
  $(selector).addEventListener('toggle', () => { if (currentEntry && !libraryOpen) draft()[field] = $(selector).open; });
}
$('#saved-query').addEventListener('input', renderLibrary);
$('#settings').addEventListener('keydown', event => {
  if (event.key === 'Escape') { $('#settings').open = false; $('#settings > summary').focus(); }
});
document.addEventListener('click', event => { if (!$('#settings').contains(event.target)) $('#settings').open = false; });
$('#destination').addEventListener('change', () => { draft().destination = $('#destination').value; updateSave(); });
$('#sense').addEventListener('change', () => { currentSense = currentEntry.senses.find(sense => sense.id === $('#sense').value); renderSense(); });
$('#save').addEventListener('click', save);
$('#keep-context').addEventListener('change', async () => {
  if (!currentEntry) return;
  if (!$('#keep-context').checked) { draft().context = ''; renderSense(); return; }
  const selectedKey = key(), version = generation;
  $('#keep-context').disabled = true;
  try {
    const text = await contextProvider();
    if (version !== generation || !currentEntry || selectedKey !== key()) return;
    draft().context = text; renderSense();
  } catch (error) { status(error.message, true); if (currentEntry && selectedKey === key()) renderSense(); }
  finally { if (currentEntry && selectedKey === key()) $('#keep-context').disabled = !contextProvider || !entrySelection; }
});
$('#library').addEventListener('click', async () => {
  if (libraryOpen) { back(); return; }
  generation++; pending?.abort(); clearTimeout(selectionTimer); lookupPending = false;
  $('#saved-query').value = '';
  const version = generation;
  try {
    const latest = await api('words');
    if (version !== generation) return;
    words = latest; renderLibrary(); status(''); $('#saved-query').focus();
  } catch (error) { if (version === generation) status(error.message, true); }
});
$('#back').addEventListener('click', back);
$('#home').addEventListener('click', goHome);
$('#theme').addEventListener('click', async () => {
  settings.theme = settings.theme === 'light' ? 'dark' : 'light'; applyTheme();
  try { await api('preferences', {theme: settings.theme}); }
  catch (error) { status('Theme changed for this session only. ' + error.message, true); }
});
$('#language').addEventListener('change', async () => {
  settings.language = $('#language').value;
  if (libraryOpen) renderLibrary(); else if (currentEntry) showEntry(currentEntry, currentSense.id);
  try { await api('preferences', {language: settings.language}); }
  catch (error) { status('Language changed for this session only. ' + error.message, true); }
});
$('#refresh').addEventListener('click', async () => { selectionText = ''; await selectionChanged(); });
$('#undo').addEventListener('click', async () => {
  const undo = undoAction; undoAction = null; clearTimeout(toastTimer); $('#toast').hidden = true;
  try { await undo?.(); } catch (error) { status('Could not undo. ' + error.message, true); }
});
$('#toast').addEventListener('focusin', () => clearTimeout(toastTimer));
$('#export').addEventListener('click', async () => {
  try {
    const latest = await api('words');
    const url = URL.createObjectURL(new Blob([JSON.stringify({version: 1, words: latest}, null, 2)], {type: 'application/json'}));
    const a = document.createElement('a'); a.href = url; a.download = 'lod-pane-vocabulary.json'; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { status('Could not export. ' + error.message, true); }
});
(async () => {
  try {
    [settings, words] = await Promise.all([api('preferences'), api('words')]);
    applyTheme(); $('#language').value = settings.language; $('#count').textContent = String(words.length);
  } catch (error) { status('Cannot open local vocabulary. ' + error.message, true); }
  if (location.pathname === '/word.html') startWord();
  else $('#connection').textContent = 'Manual lookup. In Word, open the installed add-in to follow selection.';
})();
