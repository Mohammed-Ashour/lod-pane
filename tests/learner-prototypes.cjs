// Optional browser checks. Uses external Playwright and an installed Google Chrome.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const { mkdtempSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join, resolve } = require('node:path');
const { pathToFileURL } = require('node:url');
const galleryURL = pathToFileURL(resolve(__dirname, '../learner-prototypes.html')).href;
const artifacts = mkdtempSync(join(tmpdir(), 'lod-learner-check-'));
(async () => {
  const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1150 } });
    const errors = [], requests = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()); });
    // The new study must never alter the original gallery's vocabulary or choice.
    await page.addInitScript(() => {
      if (!localStorage.getItem('lod-pane-prototypes-v1')) localStorage.setItem('lod-pane-prototypes-v1', '{"sentinel":"round-one"}');
    });
    await page.goto(galleryURL);
    const original = await page.evaluate(() => localStorage.getItem('lod-pane-prototypes-v1'));
    const selectConcept = index => page.locator(`[data-concept="${index}"]`).click();
    const chooseTheme = value => page.locator(`[data-theme-choice="${value}"]`).click();
    async function showNote(index) {
      if (index === 1) await page.locator('[data-tab="note"]').click();
      if (index === 3 && !await page.locator('#live-note').isVisible()) await page.locator('[data-section="note"] summary').click();
      if (index === 4 && await page.locator('[data-action="prepare"]').count()) await page.locator('[data-action="prepare"]').click();
    }
    assert.equal(await page.locator('#concept-nav [data-concept]').count(), 5);
    for (let index = 0; index < 5; index++) {
      await selectConcept(index);
      await page.getByRole('button', { name: 'Look up fläisseg', exact: true }).click();
      await showNote(index);
      await page.locator('#live-note').fill(`Memory cue ${index + 6}`);
      await page.locator('[data-field="destination"]').selectOption('Favorites');
      await chooseTheme('dark');
      assert.equal(await page.locator('#live-pane').getAttribute('data-theme'), 'dark');
      assert.equal(await page.locator('#live-note').inputValue(), `Memory cue ${index + 6}`);
      assert.equal(await page.locator('[data-field="destination"]').inputValue(), 'Favorites');
      await page.locator('#live-note').focus();
      await page.locator('[data-action="toggle-theme"]').click();
      assert.equal(await page.locator('#live-pane').getAttribute('data-theme'), 'light');
      assert.equal(await page.locator('#live-note').inputValue(), `Memory cue ${index + 6}`);
      await page.getByRole('button', { name: 'Save to vocabulary', exact: true }).click();
      assert.match(await page.locator('#live-pane').innerText(), /Saved to Favorites/);
      await page.locator('[data-action="saved"]').click();
      assert.match(await page.locator('.saved-note').innerText(), new RegExp(`Memory cue ${index + 6}`));
      assert.match(await page.locator('.entry-translation').innerText(), /Favorites/);
      await chooseTheme('dark');
      assert.equal(await page.locator('.saved-note').count(), 1, 'theme shares the saved vocabulary');
      await page.locator('[data-action="back"]').click();
      await showNote(index);
      await page.locator('#live-note').fill(`Updated cue ${index + 6}`);
      await page.getByRole('button', { name: 'Update saved word', exact: true }).click();
      await page.locator('[data-action="saved"]').click();
      assert.match(await page.locator('.saved-note').innerText(), /Updated cue/);
      await page.locator('#undo-button').click();
      assert.match(await page.locator('.saved-note').innerText(), /Memory cue/);
      await page.locator('[data-remove="fläisseg"]').click();
      assert.equal(await page.locator('.saved-entry').count(), 0);
      await page.locator('#undo-button').click();
      assert.equal(await page.locator('.saved-entry').count(), 1);
      await page.locator('[data-action="back"]').click();
    }
    // All learning tools have the same draft behavior, regardless of organization.
    await selectConcept(1);
    await page.locator('[data-tab="note"]').click();
    await page.locator('#live-note').fill('Draft survives tabs and words.');
    await page.locator('[data-tab="note"]').focus();
    await page.keyboard.press('ArrowLeft');
    assert.equal(await page.locator('[data-tab="grammar"]').getAttribute('aria-selected'), 'true');
    assert.match(await page.locator('[role="tabpanel"]').innerText(), /fläisseg/);
    await page.keyboard.press('End');
    assert.equal(await page.locator('#live-note').inputValue(), 'Draft survives tabs and words.');
    await page.getByRole('button', { name: 'Look up heem', exact: true }).click();
    await page.getByRole('button', { name: 'Look up fläisseg', exact: true }).click();
    await page.locator('[data-tab="note"]').click();
    assert.equal(await page.locator('#live-note').inputValue(), 'Draft survives tabs and words.');
    await page.locator('[data-field="lang"]').selectOption('fr');
    assert.equal(await page.locator('.meaning').innerText(), 'appliqué, assidu');
    // Sentence capture is opt-in and independently verified in saved vocabulary.
    await selectConcept(2);
    await page.getByRole('button', { name: 'Look up gemittlech', exact: true }).click();
    assert.equal(await page.locator('[data-field="includeContext"]').isChecked(), false);
    await page.locator('[data-field="includeContext"]').check();
    await page.locator('#live-note').fill('A café word.');
    await page.getByRole('button', { name: 'Save to vocabulary', exact: true }).click();
    await page.locator('[data-action="saved"]').click();
    assert.equal(await page.locator('.saved-context').innerText(), 'Am Café ass et gemittlech.');
    await page.locator('[data-action="back"]').click();
    await page.locator('[data-field="includeContext"]').uncheck();
    await page.getByRole('button', { name: 'Update saved word', exact: true }).click();
    await page.locator('[data-action="saved"]').click();
    assert.equal(await page.locator('.saved-context').count(), 0);
    // A two-step capture never saves just by opening the form or navigating back.
    await selectConcept(4);
    await page.getByRole('button', { name: 'Look up heem', exact: true }).click();
    await page.locator('[data-action="prepare"]').click();
    await page.locator('#live-note').fill('An unfinished draft.');
    await page.locator('[data-action="read"]').click();
    assert.match(await page.locator('[data-action="saved"]').getAttribute('aria-label'), /1 saved/);
    await page.locator('[data-action="prepare"]').click();
    assert.equal(await page.locator('#live-note').inputValue(), 'An unfinished draft.');
    await page.locator('[data-action="saved"]').click();
    assert.equal(await page.locator('[data-revisit="heem"]').count(), 0);
    // Empty, loading, unavailable and unknown lookups in either theme.
    for (const value of ['light', 'dark']) {
      await chooseTheme(value);
      for (const state of ['empty', 'loading', 'missing', 'offline']) {
        await page.locator('#state-select').selectOption(state);
        assert.equal(await page.locator('.state-view').count(), 1);
        assert.equal(await page.locator('[data-action="save"]').count(), 0);
      }
      await page.locator('[data-action="retry"]').click();
    }
    await page.locator('#live-pane input[name="word"]').fill('<img src=x onerror=alert(1)>');
    await page.locator('#live-pane input[name="word"]').press('Enter');
    assert.match(await page.locator('.state-view h3').innerText(), /<img/);
    assert.equal(await page.locator('#live-pane img').count(), 0);
    await page.getByRole('button', { name: 'LibreOffice', exact: true }).click();
    assert.match(await page.locator('#document-name').innerText(), /\.odt$/);
    // Browser range selection and keyboard activation use the same lookup path.
    await page.locator('[data-word="wieder"]').evaluate(el => {
      const range = document.createRange(); range.selectNodeContents(el);
      const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
      el.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
    });
    await page.waitForFunction(() => document.querySelector('#live-pane .headword')?.textContent === 'Wieder');
    await page.evaluate(() => window.getSelection().removeAllRanges());
    await page.locator('[data-word="spadséiergang"]').focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#live-pane .headword').innerText(), 'Spadséiergang');
    // Theme and layout preference survive reload. Unsaved drafts deliberately do not.
    await selectConcept(1); await chooseTheme('dark');
    await page.locator('#choose-button').click();
    await page.reload();
    assert.equal(await page.locator('#live-pane').getAttribute('data-theme'), 'dark');
    await selectConcept(1);
    assert.match(await page.locator('#choose-button').innerText(), /Your chosen direction/);
    await page.locator('[data-action="saved"]').click();
    assert.match(await page.locator('.saved-note').innerText(), /Memory cue 7/);
    await page.locator('[data-action="back"]').click();
    // Screenshots and layout checks cover all ten layout/theme combinations.
    await selectConcept(0); await chooseTheme('light');
    await page.evaluate(() => scrollTo(0, 0));
    await page.waitForTimeout(180);
    await page.screenshot({ path: join(artifacts, 'open-light.png'), fullPage: true });
    await chooseTheme('dark');
    await page.evaluate(() => scrollTo(0, 0));
    await page.waitForTimeout(180);
    await page.screenshot({ path: join(artifacts, 'open-dark.png'), fullPage: true });
    await page.locator('#compare-button').click();
    assert.equal(await page.locator('.comparison').count(), 5);
    for (const value of ['light', 'dark']) {
      await page.locator(`[data-compare-theme="${value}"]`).click();
      assert.equal(await page.locator(`.mini-frame .pane[data-theme="${value}"]`).count(), 5);
      await page.screenshot({ path: join(artifacts, `comparison-${value}.png`), fullPage: true });
    }
    await page.locator('[data-open-concept="2"]').click();
    assert.equal(await page.locator('#concept-title').innerText(), 'Sentence notebook');
    assert.equal(await page.locator('#live-pane').getAttribute('data-theme'), 'dark');
    for (const width of [1440, 1280, 1024, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1100 });
      for (let index = 0; index < 5; index++) {
        await selectConcept(index);
        await page.getByRole('button', { name: 'Look up Spadséiergang', exact: true }).click();
        for (const value of ['light', 'dark']) {
          await chooseTheme(value);
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `page overflow ${width}, ${index}, ${value}`);
          assert.equal(await page.locator('#live-pane').evaluate(el => el.scrollWidth > el.clientWidth), false, `pane overflow ${width}, ${index}, ${value}`);
          assert.equal(await page.locator('#live-pane [data-action="prepare"], #live-pane [data-action="save"]').isVisible(), true, 'save controls stay visible');
          assert.ok(await page.locator('#live-pane').evaluate(el => {
            const pane = el.getBoundingClientRect(), footer = el.querySelector('.pane-footer').getBoundingClientRect();
            const workspace = el.parentElement.getBoundingClientRect();
            return footer.bottom <= pane.bottom + 1 && pane.bottom <= workspace.bottom + 1;
          }), `pane and save footer fit inside workspace ${width}, ${index}, ${value}`);
        }
      }
      if (width === 390) await page.screenshot({ path: join(artifacts, 'mobile-dark.png'), fullPage: true });
    }
    await page.locator('#compare-button').click();
    assert.equal(await page.locator('#compare-dialog').evaluate(el => el.scrollWidth > el.clientWidth), false);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#compare-dialog').evaluate(el => el.open), false);
    assert.equal(await page.evaluate(() => localStorage.getItem('lod-pane-prototypes-v1')), original);
    const fallback = await browser.newPage();
    fallback.on('pageerror', error => errors.push(error.message));
    await fallback.addInitScript(() => Object.defineProperty(window, 'localStorage', { get() { throw Error('Blocked for test'); } }));
    await fallback.goto(galleryURL);
    assert.equal(await fallback.locator('#storage-warning').isVisible(), true);
    await fallback.locator('#live-note').fill('Works without browser storage.');
    await fallback.getByRole('button', { name: 'Save to vocabulary', exact: true }).click();
    assert.match(await fallback.locator('#live-pane').innerText(), /Saved to Study/);
    assert.deepEqual(errors, []); assert.deepEqual(requests, []);
    console.log('PASS: five learner layouts in both themes; note/destination preservation; save/update/remove/undo; tab keyboard behavior; per-word drafts; opt-in context; two-step capture; error previews; escaping; selection; host simulation; persistence; comparison; blocked storage; 60 responsive layouts. Round-one data unchanged. No browser errors or network requests.');
    console.log('Screenshots: ' + artifacts);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
