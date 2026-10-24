// Optional browser checks. See README.md for the external Playwright install command.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const { mkdtempSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join, resolve } = require('node:path');
const { pathToFileURL } = require('node:url');
const artifacts = mkdtempSync(join(tmpdir(), 'lod-pane-check-'));
const galleryURL = pathToFileURL(resolve(__dirname, '../prototypes.html')).href;
(async()=>{
const browser = await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'chrome',headless:true});
try {
const page = await browser.newPage({viewport:{width:1440,height:1100},deviceScaleFactor:1});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const requests=[];page.on('request',r=>{if(/^https?:/.test(r.url()))requests.push(r.url());});
await page.goto(galleryURL);
await page.screenshot({path:join(artifacts,'desktop.png'),fullPage:true});
// Real text selection dispatches the same pointer event used by a drag selection.
await page.locator('[data-word="gemittlech"]').evaluate(el=>{
 const range=document.createRange();range.selectNodeContents(el);
 const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
 el.dispatchEvent(new PointerEvent('pointerup',{bubbles:true}));
});
await page.waitForFunction(()=>document.querySelector('#live-pane .headword')?.textContent==='gemittlech');
await page.evaluate(()=>window.getSelection().removeAllRanges());
await page.locator('[data-word="wieder"]').focus();
await page.keyboard.press('Enter');
assert.equal(await page.locator('#live-pane .headword').innerText(),'Wieder');
await page.getByRole('button',{name:'Save to vocabulary',exact:true}).click();
assert.match(await page.locator('#live-pane').innerText(),/Saved to Study/);
await page.getByRole('button',{name:'View 1 saved words'}).click();
assert.match(await page.locator('#live-pane').innerText(),/Your vocabulary 1/);
await page.getByRole('button',{name:'Back to lookup'}).click();
await page.getByRole('button',{name:'Remove saved word'}).click();
assert.match(await page.locator('#live-pane').innerText(),/Save to vocabulary/);
await page.getByRole('button',{name:'Look up Spadséiergang',exact:true}).click();
assert.equal(await page.locator('#live-pane .headword').innerText(),'Spadséiergang');
await page.locator('#live-pane [data-field="lang"]').selectOption('fr');
assert.equal(await page.locator('#live-pane .meaning').innerText(),'promenade');
await page.locator('[data-concept="1"]').click();
await page.getByRole('button',{name:'Look up gemittlech',exact:true}).click();
await page.locator('[data-field="includeContext"]').check();
await page.getByRole('button',{name:'Save to vocabulary',exact:true}).click();
await page.locator('#live-pane [data-action="saved"]').click();
assert.equal(await page.locator('.saved-context').innerText(),'“Am Café ass et gemittlech.”');
await page.locator('[data-concept="2"]').click();
for(const word of ['Wieder','Spadséiergang']){
 await page.getByRole('button',{name:'Look up '+word,exact:true}).click();
 await page.getByRole('button',{name:'Save to vocabulary',exact:true}).click();
}
assert.equal(await page.locator('.session-row').count(),2);
await page.locator('.session-row').filter({hasText:'Wieder'}).click();
assert.equal(await page.locator('#live-pane .headword').innerText(),'Wieder');
await page.locator('[data-concept="3"]').click();
await page.getByRole('button',{name:'Look up fläisseg',exact:true}).click();
await page.getByText('Grammar & a personal note',{exact:true}).click();
await page.locator('#word-note').fill('Remember it with léieren.');
await page.locator('[data-field="destination"]').selectOption('Favorites');
await page.getByRole('button',{name:'Save to vocabulary',exact:true}).click();
await page.locator('#live-pane [data-action="saved"]').click();
assert.match(await page.locator('.saved-note').innerText(),/Remember it with léieren/);
assert.match(await page.locator('.entry-translation').innerText(),/Favorites/);
await page.getByRole('button',{name:'Back to lookup'}).click();
if(!await page.locator('#word-note').isVisible())await page.getByText('Grammar & a personal note',{exact:true}).click();
await page.locator('#word-note').fill('An updated memory cue.');
await page.getByRole('button',{name:'Update saved word',exact:true}).click();
await page.locator('#live-pane [data-action="saved"]').click();
assert.match(await page.locator('.saved-note').innerText(),/An updated memory cue/);
await page.locator('#undo-button').click();
assert.match(await page.locator('.saved-note').innerText(),/Remember it with léieren/);
await page.locator('[data-concept="4"]').click();
await page.locator('[data-action="pin"]').click();
await page.getByRole('button',{name:'Look up heem',exact:true}).click();
assert.equal(await page.locator('#live-pane .headword').innerText(),'Wieder');
assert.match(await page.locator('.pending-word').innerText(),/heem/);
assert.equal(await page.locator('[data-word="heem"]').getAttribute('aria-pressed'),'true');
assert.equal(await page.locator('[data-word="wieder"]').getAttribute('aria-pressed'),'false');
assert.equal(await page.locator('[data-action="pending"]').evaluate(el=>el===document.activeElement),false,'document selection does not steal focus into the pinned pane');
await page.locator('[data-action="pending"]').click();
assert.equal(await page.locator('#live-pane .headword').innerText(),'heem');
await page.getByRole('button',{name:'LibreOffice',exact:true}).click();
assert.match(await page.locator('#document-name').innerText(),/\.odt$/);
for(const state of ['empty','loading','missing','offline']){
 await page.locator('#state-select').selectOption(state);
 assert.equal(await page.locator('#live-pane .state-view').count(),1);
}
await page.locator('[data-action="retry"]').click();
await page.locator('#live-pane input[name="word"]').fill('<script>bad</script>');
await page.locator('#live-pane input[name="word"]').press('Enter');
assert.match(await page.locator('.state-view h3').innerText(),/<script>bad<\/script>/);
assert.equal(await page.locator('#live-pane script').count(),0);
await page.locator('#live-pane input[name="word"]').fill('Wieder');
await page.locator('#live-pane input[name="word"]').press('Enter');
await page.locator('#choose-button').click();
await page.reload();
await page.locator('[data-concept="4"]').click();
assert.match(await page.locator('#choose-button').innerText(),/Your chosen direction/);
await page.locator('[data-concept="1"]').click();
await page.locator('#live-pane [data-action="saved"]').click();
assert.equal(await page.locator('.saved-context').count(),1);
await page.locator('#compare-button').click();
assert.equal(await page.locator('#compare-grid .comparison').count(),5);
await page.screenshot({path:join(artifacts,'comparison.png'),fullPage:true});
for(const frame of await page.locator('.mini-frame').all()){
 const gap=await frame.evaluate(el=>Math.abs(el.clientWidth-el.querySelector('.pane').getBoundingClientRect().width));
 assert.ok(gap<2,'comparison thumbnail fills its frame');
}
await page.locator('[data-open-concept="4"]').click();
assert.equal(await page.locator('#concept-title').innerText(),'Night companion');
await page.locator('[data-concept="0"]').click();
for(const width of [1440,1280,1024,768,390,320]){
 await page.setViewportSize({width,height:1000});
 for(let i=0;i<5;i++){
  await page.locator(`[data-concept="${i}"]`).click();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`page overflow ${width}, concept ${i}`);
  assert.equal(await page.locator('#live-pane').evaluate(el=>el.scrollWidth>el.clientWidth),false,`pane overflow ${width}, concept ${i}`);
 }
 if(width===390){await page.locator('[data-concept="0"]').click();await page.screenshot({path:join(artifacts,'mobile.png'),fullPage:true});}
}
await page.setViewportSize({width:390,height:1000});
await page.locator('#compare-button').click();
assert.equal(await page.locator('#compare-dialog').evaluate(el=>el.scrollWidth>el.clientWidth),false,'comparison dialog mobile overflow');
await page.keyboard.press('Escape');
assert.equal(await page.locator('#compare-dialog').evaluate(el=>el.open),false);
const fallback = await browser.newPage();
fallback.on('pageerror',e=>errors.push(e.message));
await fallback.addInitScript(()=>Object.defineProperty(window,'localStorage',{get(){throw new Error('Storage blocked for test');}}));
await fallback.goto(galleryURL);
assert.equal(await fallback.locator('#storage-warning').isVisible(),true);
await fallback.getByRole('button',{name:'Save to vocabulary',exact:true}).click();
assert.match(await fallback.locator('#live-pane').innerText(),/Saved to Study/);
assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
console.log('PASS: five concepts; click, text and keyboard selection; save/remove/undo; languages; context; recent saves; note updates and undo; pinning; host switch; error states; escaping; persistence; comparison; blocked storage; 30 responsive layouts. No page errors or network requests.');
console.log('Screenshots: '+artifacts);
} finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exit(1);});
