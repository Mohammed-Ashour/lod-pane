// Optional Playwright check. Runs the developer-only loopback mirror with a fixture
// dictionary and an Office.js boundary stub. It does not test a real Word installation.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const { spawn, execFileSync } = require('node:child_process');
const { mkdtempSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join, resolve } = require('node:path');
const artifacts = mkdtempSync(join(tmpdir(), 'lod-runtime-'));
const cert = join(artifacts, 'cert.pem'), key = join(artifacts, 'key.pem');
execFileSync('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', key, '-out', cert, '-days', '1', '-subj', '/CN=localhost'], {stdio: 'ignore'});
const server = spawn(process.env.PYTHON || 'python3', ['tests/test_runtime.py', '--serve', '--cert', cert, '--key', key, '--port', String(process.env.LOD_TEST_PORT || 43127)], {
  cwd: resolve(__dirname, '..'), env: {...process.env, LOD_PANE_DATA_DIR: join(artifacts, 'data'), PYTHONUNBUFFERED: '1'}, stdio: ['ignore', 'pipe', 'pipe']
});
let output = ''; server.stdout.on('data', value => output += value); server.stderr.on('data', value => output += value);
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
const officeStub = `
window.mockSelection = 'Wieder';
window.mockParagraph = "Haut ass d'Wieder schéin.";
window.mockLocation = 1;
window.mockTrackedRanges = 0;
window.mockInsertions = 0;
window.mockReadOnly = false;
window.mockUndoStack = [];
window.mockUndoDocument = () => { const previous=window.mockUndoStack.pop(); if(previous)Object.assign(window,previous); };
window.Office = {
 HostType: {Word:'Word'}, EventType: {DocumentSelectionChanged:'selection'},
 AsyncResultStatus:{Succeeded:'succeeded'}, CoercionType:{Text:'text'}, DocumentMode:{ReadOnly:'readOnly'},
 onReady: async()=>({host:'Word'}),
 context:{document:{
  get mode(){return window.mockReadOnly?'readOnly':'readWrite';},
  getSelectedDataAsync(type,callback){callback({status:'succeeded',value:window.mockSelection});},
  addHandlerAsync(type,callback,done){window.selectionHandler=callback;done({status:'succeeded'});}
 }}
};
window.Word={InsertLocation:{replace:'Replace'},run:async(first,second)=>(second||first)({
 sync:async()=>{if(window.mockSyncGate)await window.mockSyncGate;},
 document:{getSelection:()=>{
  const range={text:window.mockSelection,location:window.mockLocation,tracked:false,load(){},
   track(){this.tracked=true;window.mockTrackedRanges++;},
   untrack(){if(this.tracked){this.tracked=false;window.mockTrackedRanges--;}},
   compareLocationWith(other){return {value:this.location===other.location?'Equal':'Disjoint'};},
   insertText(text,where){
    if(window.mockReadOnly)throw new Error('Document is read-only.');
    if(where!=='Replace')throw new Error('Expected a range replacement.');
    window.mockUndoStack.push({mockSelection:window.mockSelection,mockParagraph:window.mockParagraph});
    window.mockParagraph=window.mockParagraph.replace(this.text,text);
    window.mockSelection=text;window.mockInsertions++;
   },
   paragraphs:{getFirst:()=>({text:window.mockParagraph,load(){}})}
  };return range;
 }}
})};
`;
(async () => {
  let browser;
  try {
    for (let i=0; i<100 && !output.includes('Word companion at'); i++) {
      if (server.exitCode !== null) throw Error(output);
      await wait(50);
    }
    if (!output.includes('Word companion at')) throw Error('HTTPS test server did not start: '+output);
    const port = process.env.LOD_TEST_PORT || 43127;
    browser = await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'chrome'});
    const page = await browser.newPage({ignoreHTTPSErrors:true,viewport:{width:336,height:800}});
    const errors=[]; page.on('pageerror', error=>errors.push(error.message));
    await page.route('https://appsforoffice.microsoft.com/**', route=>route.fulfill({contentType:'text/javascript',body:officeStub}));
    await page.goto(`https://localhost:${port}/word.html`);
    await page.waitForFunction(()=>document.querySelector('#headword').textContent==='Wieder'&&!document.querySelector('#entry').hidden);
    assert.match(await page.locator('#connection').textContent(), /Following your Word selection/);
    assert.equal(await page.locator('#note').isVisible(),false);
    assert.equal(await page.locator('#keep-context').isVisible(),false);
    assert.equal(await page.locator('#status').innerText(),'');
    await page.screenshot({path:join(artifacts,'word-reading.png'),fullPage:true});
    await page.locator('#settings > summary').focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#theme').isVisible(),true);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#theme').isVisible(),false);
    assert.equal(await page.locator('#settings > summary').evaluate(node=>node===document.activeElement),true);
    const toggleTheme=async()=>{await page.locator('#settings > summary').click();await page.locator('#theme').click();await page.keyboard.press('Escape');};
    await page.locator('#note-details > summary').click();
    assert.equal(await page.locator('#meaning').innerText(),'weather');
    assert.equal(await page.locator('#sense option').count(),3);
    assert.equal(await page.locator('#keep-context').isChecked(),false);
    await page.locator('#note').fill('My weather note.');
    await page.locator('#destination').selectOption('Favorites');
    await toggleTheme();
    assert.equal(await page.locator('#note').inputValue(),'My weather note.');
    assert.equal(await page.locator('#destination').inputValue(),'Favorites');
    await page.locator('#context-details > summary').click();
    await page.evaluate(()=>{window.mockParagraph='x'.repeat(1200)+'Wieder';});
    await page.locator('#keep-context').check();
    const longContext=await page.locator('#context').innerText();
    assert.equal(longContext.length,1000);
    assert.ok(longContext.endsWith('Wieder'),'long context stays anchored to the selected word');
    await page.locator('#keep-context').uncheck();
    await page.evaluate(()=>{window.mockParagraph="Haut ass d'Wieder schéin.";});
    await page.locator('#keep-context').check();
    assert.equal(await page.locator('#context').innerText(),"Haut ass d'Wieder schéin.");
    const firstSave=page.waitForRequest(request=>request.url().endsWith('/api/save'));
    await page.locator('#save').click();
    assert.deepEqual(Object.keys((await firstSave).postDataJSON()).sort(),['baseUpdated','context','destination','entryId','note','senseId'],'disclosure flags must not reach storage');
    await page.waitForFunction(()=>document.querySelector('#save').textContent==='Saved to Favorites');
    await page.screenshot({path:join(artifacts,'word-dark.png'),fullPage:true});
    await page.locator('#library').click();
    await page.waitForFunction(()=>document.querySelectorAll('.saved-item').length===1);
    assert.match(await page.locator('#saved-list').innerText(), /My weather note/);
    assert.match(await page.locator('#saved-list').innerText(), /Haut ass/);
    assert.equal(await page.locator('#library').getAttribute('aria-pressed'),'true');
    await page.locator('#saved-query').fill('weather note');
    assert.equal(await page.locator('.saved-item').count(),1);
    await page.locator('#saved-query').fill('no such word');
    assert.equal(await page.locator('.saved-item').count(),0);
    assert.match(await page.locator('#saved-list').innerText(),/No saved words match/);
    await page.locator('#saved-query').fill('');
    await page.screenshot({path:join(artifacts,'word-saved.png'),fullPage:true});
    const download = page.waitForEvent('download');
    await page.locator('#export').click();
    assert.equal((await download).suggestedFilename(),'lod-pane-vocabulary.json');
    await page.locator('#back').click();
    // A second sense is a different saved word, with a separate draft.
    await page.locator('#sense').selectOption('WIEDER1UNI2');
    assert.equal(await page.locator('#note').inputValue(),'');
    assert.equal(await page.locator('#note').isVisible(),false);
    await page.locator('#note-details > summary').click();
    await page.locator('#note').fill('Second meaning.');
    await page.locator('#save').click();
    await page.waitForFunction(()=>document.querySelector('#count').textContent==='2');
    await page.locator('#library').click();
    await page.locator('#saved-query').fill('weather');
    assert.equal(await page.locator('.saved-item').count(),1,'search only the saved meaning, not its unsaved sibling senses');
    await page.locator('#back').click();
    await page.locator('#sense').selectOption('WIEDER1UNI1');
    assert.equal(await page.locator('#note').inputValue(),'My weather note.');
    // A failed write keeps the draft, and never reports Saved.
    await page.locator('#note').fill('Do not lose this draft.');
    await page.route(`**/api/save`, route=>route.fulfill({status:500,contentType:'application/json',body:JSON.stringify({error:'Disk unavailable for test.'})}));
    await page.locator('#save').click();
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Not saved'));
    assert.equal(await page.locator('#note').inputValue(),'Do not lose this draft.');
    assert.equal(await page.locator('#save').innerText(),'Save changes');
    assert.equal(await page.locator('#note-state').innerText(),'Unsaved');
    await page.unroute('**/api/save');
    // Selection is automatic, but moving focus away from text does not erase a draft.
    await page.evaluate(()=>{window.mockSelection='';window.selectionHandler();});
    await wait(300);
    assert.equal(await page.locator('#note').inputValue(),'Do not lose this draft.');
    await page.evaluate(()=>{window.mockSelection='heem';window.mockParagraph='Owes ginn ech heem.';window.selectionHandler();});
    await page.waitForFunction(()=>document.querySelector('#headword').textContent==='heem');
    assert.equal(await page.locator('#meaning').innerText(),'home');
    await page.evaluate(()=>{window.mockSelection='Wieder';window.selectionHandler();});
    await page.waitForFunction(()=>document.querySelector('#headword').textContent==='Wieder');
    assert.equal(await page.locator('#note').inputValue(),'Do not lose this draft.');
    await page.locator('#language').selectOption('fr');
    assert.match(await page.locator('#meaning').innerText(), /temps/);
    assert.equal(await page.locator('#note').inputValue(),'Do not lose this draft.');
    // Manual lookups cannot attach a different word's document paragraph.
    await page.locator('#query').fill('heem'); await page.locator('#query').press('Enter');
    await page.waitForFunction(()=>document.querySelector('#headword').textContent==='heem');
    assert.equal(await page.locator('#keep-context').isDisabled(),true);
    await page.locator('#query').fill('two words'); await page.locator('#query').press('Enter');
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Select one word'));
    assert.equal(await page.locator('#capture').isVisible(),false);
    await page.locator('#query').fill('<script>'); await page.locator('#query').press('Enter');
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Select one word'));
    assert.equal(await page.locator('#entry script').count(),0);
    await page.locator('#query').fill('Wieder'); await page.locator('#query').press('Enter');
    await page.waitForFunction(()=>!document.querySelector('#entry').hidden);
    // Responsive sidebar, fixed save controls, and both themes.
    for(const width of [240,288,320,336,400]){
      await page.setViewportSize({width,height:700});
      for(let i=0;i<2;i++){
        await toggleTheme();
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
        const box=await page.locator('#save').boundingBox();
        assert.ok(box.y>=0 && box.y+box.height<=700, 'Save stays inside the viewport');
      }
    }
    await page.setViewportSize({width:336,height:800});
    if(await page.locator('html').getAttribute('data-theme')!=='light')await toggleTheme();
    await page.screenshot({path:join(artifacts,'word-light.png'),fullPage:true});
    await page.reload();
    await page.waitForFunction(()=>!document.querySelector('#entry').hidden);
    assert.equal(await page.locator('#note').inputValue(),'My weather note.','only explicit saves survive reload');
    assert.equal(await page.locator('#note').isVisible(),true,'saved notes reveal automatically');
    assert.equal(await page.locator('#context').isVisible(),true,'saved excerpts reveal automatically');
    await page.locator('#library').click();
    await page.locator('.remove').first().click();
    await page.locator('#undo').click();
    await page.waitForFunction(()=>document.querySelector('#count').textContent==='2');
    assert.deepEqual(errors,[]);
    // Missing fields and failures must not reuse the initial onboarding state.
    await page.route('**/api/lookup?word=missing', route=>route.fulfill({contentType:'application/json',body:JSON.stringify({candidates:[]})}));
    await page.locator('#query').fill('missing');await page.locator('#query').press('Enter');
    await page.waitForFunction(()=>document.querySelector('#empty h1').textContent==='No match found.');
    await page.route('**/api/lookup?word=failed', route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Dictionary unavailable.'})}));
    await page.locator('#query').fill('failed');await page.locator('#query').press('Enter');
    await page.waitForFunction(()=>document.querySelector('#empty h1').textContent==='Could not look up this word.');
    assert.equal(await page.locator('#capture').isVisible(),false);
    assert.equal(await page.locator('#lookup-view').getAttribute('aria-busy'),'false');
    await page.locator('#library').click();
    await page.locator('.open-word').first().click();
    assert.equal(await page.locator('#library').getAttribute('aria-pressed'),'false');
    const sparse={id:'SPARSE',word:'Luxembourgish'.repeat(5),pos:'',url:'https://lod.lu/artikel/SPARSE',senses:[{id:'SPARSE1',translations:{en:'A long translation '.repeat(35)},grammar:'',example:''}]};
    await page.route('**/api/lookup?word=sparse', route=>route.fulfill({contentType:'application/json',body:JSON.stringify({entry:sparse})}));
    await page.locator('#query').fill('sparse');await page.locator('#query').press('Enter');
    await page.waitForFunction(()=>document.querySelector('#headword').textContent.startsWith('Luxembourgish'));
    assert.equal(await page.locator('#grammar-block').isVisible(),false);
    assert.equal(await page.locator('#example-block').isVisible(),false);
    assert.equal(await page.locator('#sense-row').isVisible(),false);
    assert.equal(await page.locator('#note').isVisible(),false);
    await page.setViewportSize({width:240,height:500});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    const saveBox=await page.locator('#save').boundingBox();
    assert.ok(saveBox.y+saveBox.height<=500);
    // Home clears the view, not notes/vocabulary, and cancels late lookups.
    await page.setViewportSize({width:336,height:800});
    await page.locator('#home').click();
    assert.equal(await page.locator('#empty').isVisible(),true);
    assert.equal(await page.locator('#entry').isVisible(),false);
    assert.equal(await page.locator('#capture').isVisible(),false);
    assert.equal(await page.locator('#query').inputValue(),'');
    const lookupWord=async word=>{
      await page.locator('#query').fill(word);await page.locator('#query').press('Enter');
      await page.waitForFunction(word=>document.querySelector('#headword').textContent===word&&!document.querySelector('#entry').hidden,word);
    };
    await lookupWord('Wieder');
    assert.equal(await page.locator('#note').inputValue(),'My weather note.');
    await page.locator('#note').fill('Keep this unsaved draft through Home.');
    await page.locator('#home').click();
    await lookupWord('Wieder');
    assert.equal(await page.locator('#note').inputValue(),'Keep this unsaved draft through Home.');
    const openReplacement=async()=>{
      if(await page.locator('#replace-details').getAttribute('open')!==null)await page.locator('#replace-details > summary').click();
      await page.locator('#replace-details > summary').click();
      await page.waitForFunction(()=>{const message=document.querySelector('#replace-status').textContent;return document.querySelector('#replace-details').open&&message&&!message.includes('Reading');});
    };
    // Preparing a preview never edits. Surrounding whitespace is preserved.
    await page.evaluate(()=>{window.mockSelection='  Wierder ';window.mockParagraph='  Wierder ass schéin.';window.mockLocation=10;});
    await openReplacement();
    assert.equal(await page.locator('#replace-before').textContent(),'  Wierder ');
    assert.equal(await page.locator('#replace-after').textContent(),'  Wieder ');
    assert.equal(await page.evaluate(()=>window.mockInsertions),0);
    await page.screenshot({path:join(artifacts,'word-replace.png'),fullPage:true});
    await page.locator('#replace-confirm').click();
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Selection replaced'));
    assert.equal(await page.evaluate(()=>window.mockParagraph),'  Wieder ass schéin.');
    assert.equal(await page.evaluate(()=>window.mockInsertions),1);
    await page.waitForFunction(()=>window.mockTrackedRanges===0);
    await page.evaluate(()=>window.mockUndoDocument());
    assert.equal(await page.evaluate(()=>window.mockParagraph),'  Wierder ass schéin.','replacement is one host edit that can be undone');
    // A different occurrence of identical text is not the previewed range.
    await openReplacement();
    await page.evaluate(()=>window.mockLocation++);
    await page.locator('#replace-confirm').click();
    await page.waitForFunction(()=>document.querySelector('#replace-status').textContent.includes('selection changed'));
    assert.equal(await page.evaluate(()=>window.mockInsertions),1);
    // Text changes at the same location are also rejected.
    await openReplacement();
    await page.evaluate(()=>{window.mockSelection='heem';});
    await page.locator('#replace-confirm').click();
    await page.waitForFunction(()=>document.querySelector('#replace-status').textContent.includes('selection changed'));
    assert.equal(await page.evaluate(()=>window.mockInsertions),1);
    await openReplacement();
    await page.evaluate(()=>{window.mockReadOnly=true;});
    await page.locator('#replace-confirm').click();
    await page.waitForFunction(()=>document.querySelector('#replace-status').textContent.includes('read-only'));
    assert.equal(await page.evaluate(()=>window.mockInsertions),1,'write permission is checked again at confirmation');
    await openReplacement();
    assert.match(await page.locator('#replace-status').innerText(),/read-only/);
    assert.equal(await page.locator('#replace-confirm').isDisabled(),true);
    await page.evaluate(()=>{window.mockReadOnly=false;window.mockSelection='';});
    await openReplacement();
    assert.match(await page.locator('#replace-status').innerText(),/Select one word/);
    await page.evaluate(()=>{window.mockSelection='Wieder';});
    await openReplacement();
    assert.equal(await page.locator('#replace-confirm').isDisabled(),true,'matching headword is a no-op');
    // Cancelling a preview during the guard read must not untrack an active context or edit.
    await page.evaluate(()=>{window.mockSelection='Wierder';});
    await openReplacement();
    await page.evaluate(()=>{window.mockSyncGate=new Promise(resolve=>window.releaseMockSync=resolve);});
    await page.locator('#replace-confirm').click();
    await page.locator('#query').fill('missing');await page.locator('#query').press('Enter');
    await page.waitForFunction(()=>document.querySelector('#empty h1').textContent==='No match found.');
    assert.equal(await page.evaluate(()=>window.mockTrackedRanges),1,'an in-flight write context keeps its range until it returns');
    await page.evaluate(()=>{window.releaseMockSync();window.mockSyncGate=null;});
    await page.waitForFunction(()=>window.mockTrackedRanges===0&&!document.querySelector('#home').disabled);
    assert.equal(await page.evaluate(()=>window.mockInsertions),1);
    await lookupWord('Wieder');
    // Closing/Home releases captured ranges and invalidates delayed previews.
    await openReplacement();
    await page.locator('#home').click();
    await page.waitForFunction(()=>window.mockTrackedRanges===0);
    assert.equal(await page.locator('#entry').isVisible(),false);
    await lookupWord('Wieder');
    await page.evaluate(()=>{window.mockSyncGate=new Promise(resolve=>window.releaseMockSync=resolve);});
    await page.locator('#replace-details > summary').click();
    await page.locator('#home').click();
    await page.evaluate(()=>{window.releaseMockSync();window.mockSyncGate=null;});
    await page.waitForFunction(()=>window.mockTrackedRanges===0);
    assert.equal(await page.locator('#entry').isVisible(),false);
    assert.equal(await page.evaluate(()=>window.mockInsertions),1);
    await page.locator('#library').click();
    assert.equal(await page.locator('.saved-item').count(),2);
    await page.locator('#home').click();
    assert.equal(await page.locator('#empty').isVisible(),true);
    assert.equal(await page.locator('#saved-view').isVisible(),false);
    // An outstanding dictionary response must not reopen the entry after Home.
    let finishLate;
    await page.route('**/api/lookup?word=late', async route=>{await new Promise(resolve=>finishLate=resolve);await route.fulfill({contentType:'application/json',body:JSON.stringify({entry:sparse})}).catch(()=>{});});
    await page.locator('#query').fill('late');await page.locator('#query').press('Enter');
    while(!finishLate)await wait(10);
    await page.locator('#home').click();finishLate();await wait(100);
    assert.equal(await page.locator('#entry').isVisible(),false);
    assert.equal(await page.locator('#lookup-view').getAttribute('aria-busy'),'false');
    let finishLibrary;
    await page.route('**/api/words', async route=>{await new Promise(resolve=>finishLibrary=resolve);await route.fulfill({contentType:'application/json',body:'[]'});});
    await page.locator('#library').click();
    while(!finishLibrary)await wait(10);
    await page.locator('#home').click();finishLibrary();await wait(100);
    assert.equal(await page.locator('#saved-view').isVisible(),false,'Home also cancels pending Saved navigation');
    assert.deepEqual(errors,[]);
    console.log('PASS: reading-first pane, anchored context, optimistic saves, explicit tracked-range replacement/guards/cleanup, Home cancellation with draft preservation, and existing vocabulary/responsive flows. Office and its Undo are boundary stubs, not real Word.');
    console.log('Screenshots: '+artifacts);
  } finally {
    if(browser)await browser.close();
    server.kill('SIGTERM');
  }
})().catch(error=>{console.error(error);console.error(output);process.exitCode=1;});
