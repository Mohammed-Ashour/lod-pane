#!/usr/bin/env node
// Builds fixture-backed UI media for the README. This is not real Word acceptance.
// Run with: PLAYWRIGHT_MODULE=/path/to/playwright node tests/readme-media.cjs
'use strict';
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { execFileSync, spawn } = require('node:child_process');
const { mkdirSync, mkdtempSync, rmSync, statSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join, resolve } = require('node:path');

const ROOT = resolve(__dirname, '..');
const MEDIA_DIR = join(ROOT, 'docs', 'media');
const ARTIFACTS = mkdtempSync(join(tmpdir(), 'lod-readme-media-'));
const VIEWPORT = { width: 336, height: 800 };
const PORT = Number(process.env.LOD_TEST_PORT || 43127);
const wait = milliseconds => new Promise(done => setTimeout(done, milliseconds));

const officeStub = `
window.mockSelection = 'Wieder';
window.mockParagraph = "Haut ass d'Wieder schéin.";
window.mockLocation = 1;
window.mockTrackedRanges = 0;
window.mockInsertions = 0;
window.mockReadOnly = false;
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
 sync:async()=>{},
 document:{getSelection:()=>{
  const range={text:window.mockSelection,location:window.mockLocation,tracked:false,load(){},
   track(){this.tracked=true;window.mockTrackedRanges++;},
   untrack(){if(this.tracked){this.tracked=false;window.mockTrackedRanges--;}},
   compareLocationWith(other){return {value:this.location===other.location?'Equal':'Disjoint'};},
   insertText(text,where){
    if(window.mockReadOnly)throw new Error('Document is read-only.');
    if(where!=='Replace')throw new Error('Expected a range replacement.');
    window.mockParagraph=window.mockParagraph.replace(this.text,text);
    window.mockSelection=text;window.mockInsertions++;
   },
   paragraphs:{getFirst:()=>({text:window.mockParagraph,load(){}})}
  };return range;
 }}
})};
`;

async function startFixtureServer() {
  const cert = join(ARTIFACTS, 'cert.pem');
  const key = join(ARTIFACTS, 'key.pem');
  execFileSync('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', key, '-out', cert, '-days', '1', '-subj', '/CN=localhost'], { stdio: 'ignore' });
  const server = spawn(process.env.PYTHON || 'python3', ['tests/test_runtime.py', '--serve', '--cert', cert, '--key', key, '--port', String(PORT)], {
    cwd: ROOT,
    env: { ...process.env, LOD_PANE_DATA_DIR: join(ARTIFACTS, 'data'), PYTHONUNBUFFERED: '1' },
    stdio: ['ignore', 'pipe', 'pipe']
  });
  let output = '';
  server.stdout.on('data', value => { output += value; });
  server.stderr.on('data', value => { output += value; });
  try {
    const deadline = Date.now() + 10_000;
    while (!output.includes('Word companion at')) {
      if (server.exitCode !== null) throw new Error('Fixture server exited:\n' + output);
      if (Date.now() > deadline) throw new Error('Fixture server did not start:\n' + output);
      await wait(50);
    }
    return server;
  } catch (error) {
    await stopFixtureServer(server);
    throw error;
  }
}

async function stopFixtureServer(server) {
  if (server.exitCode !== null || server.signalCode !== null) return;
  const exit = new Promise(resolve => server.once('exit', resolve));
  server.kill('SIGTERM');
  const exited = await Promise.race([
    exit.then(() => true),
    wait(2_000).then(() => false)
  ]);
  if (!exited) {
    const forcedExit = new Promise(resolve => server.once('exit', resolve));
    server.kill('SIGKILL');
    await forcedExit;
  }
}

function probe(file) {
  const result = JSON.parse(execFileSync('ffprobe', [
    '-v', 'error', '-select_streams', 'v:0',
    '-show_entries', 'stream=width,height:format=duration',
    '-of', 'json', file
  ], { encoding: 'utf8' }));
  return {
    width: result.streams[0].width,
    height: result.streams[0].height,
    duration: Number(result.format.duration || 0),
    bytes: statSync(file).size
  };
}

function humanBytes(bytes) {
  return `${(bytes / 1024).toFixed(bytes < 1024 * 1024 ? 0 : 1)} KiB`;
}

async function main() {
  mkdirSync(MEDIA_DIR, { recursive: true });
  let server;
  let browser;
  try {
    server = await startFixtureServer();
    browser = await chromium.launch({
      headless: true,
      channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome'
    });
    const context = await browser.newContext({
      viewport: VIEWPORT,
      deviceScaleFactor: 2,
      ignoreHTTPSErrors: true,
      recordVideo: { dir: ARTIFACTS, size: VIEWPORT }
    });
    const page = await context.newPage();
    page.setDefaultTimeout(10_000);
    const pageErrors = [];
    page.on('pageerror', error => pageErrors.push(error.message));
    await page.route('https://appsforoffice.microsoft.com/**', route => route.fulfill({ contentType: 'text/javascript', body: officeStub }));

    await page.goto(`https://localhost:${PORT}/word.html`);
    await page.waitForFunction(() => document.querySelector('#headword').textContent === 'Wieder' && !document.querySelector('#entry').hidden);
    const demoReadyAt = Date.now();
    await page.locator('#lookup-view').evaluate(node => { node.scrollTop = 0; });
    await wait(900);
    await page.screenshot({ path: join(MEDIA_DIR, 'word-lookup.png'), animations: 'disabled' });

    await page.locator('#note-details > summary').click();
    await page.locator('#note').pressSequentially('Remember the forecast.', { delay: 35 });
    await page.locator('#context-details > summary').click();
    await page.locator('#keep-context').check();
    await page.waitForFunction(() => {
      const context = document.querySelector('#context');
      return context && !context.hidden && context.textContent.includes('Wieder');
    });
    await wait(700);
    await page.locator('#note-details').evaluate(node => node.scrollIntoView({ block: 'start' }));
    await page.screenshot({ path: join(MEDIA_DIR, 'word-note-context.png'), animations: 'disabled' });
    await wait(700);

    await page.locator('#destination').selectOption('Favorites');
    await wait(500);
    await page.locator('#save').click();
    await page.waitForFunction(() => document.querySelector('#save').textContent === 'Saved to Favorites');
    await wait(900);
    await page.locator('#library').click();
    await page.waitForFunction(() => document.querySelectorAll('.saved-item').length === 1);
    const demoEndedAt = Date.now();
    await page.screenshot({ path: join(MEDIA_DIR, 'word-saved.png'), animations: 'disabled' });

    await page.locator('#back').click();
    await page.evaluate(() => { window.mockSelection = 'Wierder'; window.mockLocation = 10; });
    await page.locator('#replace-details > summary').click();
    await page.waitForFunction(() => !document.querySelector('#replace-preview').hidden && document.querySelector('#replace-before').textContent === 'Wierder');
    await page.locator('#replace-details').evaluate(node => {
      const scroller = node.closest('main');
      scroller.scrollTop += node.getBoundingClientRect().top - scroller.getBoundingClientRect().top - 24;
    });
    await page.screenshot({ path: join(MEDIA_DIR, 'word-replace.png'), animations: 'disabled' });

    if (pageErrors.length) throw new Error('Page errors: ' + pageErrors.join('; '));
    const video = page.video();
    const recordingClosedAt = Date.now();
    await page.close();
    await context.close();
    const rawVideo = await video.path();
    const trimmedVideo = join(MEDIA_DIR, 'word-demo.webm');
    const gif = join(MEDIA_DIR, 'word-demo.gif');

    const raw = probe(rawVideo);
    const actualVideoStart = recordingClosedAt - raw.duration * 1000;
    const trimStart = Math.max(0, (demoReadyAt - actualVideoStart) / 1000 + 0.1);
    const trimEnd = Math.min(raw.duration, (demoEndedAt - actualVideoStart) / 1000 + 0.8);
    if (!(trimEnd > trimStart + 1)) throw new Error('Recorded demo timing was not usable.');

    execFileSync('ffmpeg', [
      '-y', '-loglevel', 'error', '-ss', trimStart.toFixed(3), '-to', trimEnd.toFixed(3), '-i', rawVideo,
      '-an', '-c:v', 'libvpx-vp9', '-crf', '32', '-b:v', '0', '-row-mt', '1', '-deadline', 'good', '-cpu-used', '3',
      trimmedVideo
    ]);
    execFileSync('ffmpeg', [
      '-y', '-loglevel', 'error', '-i', trimmedVideo,
      '-filter_complex', '[0:v]fps=12,scale=240:-1:flags=lanczos,split[palette-source][frames];[palette-source]palettegen=max_colors=96:stats_mode=diff[palette];[frames][palette]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle',
      '-loop', '0', gif
    ]);

    const screenshots = ['word-lookup.png', 'word-note-context.png', 'word-saved.png', 'word-replace.png']
      .map(name => ({ name, ...probe(join(MEDIA_DIR, name)) }));
    for (const shot of screenshots) {
      if (shot.width !== 672 || shot.height !== 1600) throw new Error(`${shot.name} is ${shot.width}x${shot.height}, expected 672x1600.`);
    }
    const videoInfo = probe(trimmedVideo);
    const gifInfo = probe(gif);
    if (gifInfo.bytes >= 4 * 1024 * 1024) throw new Error(`word-demo.gif is ${humanBytes(gifInfo.bytes)}, above the 4 MiB target.`);
    if (Math.abs(videoInfo.duration - gifInfo.duration) > 0.25) throw new Error('WebM and GIF durations diverged.');

    const rows = [
      ...screenshots.map(item => `docs/media/${item.name}\t${item.width}x${item.height}\t${humanBytes(item.bytes)}`),
      `docs/media/word-demo.webm\t${videoInfo.width}x${videoInfo.height}\t${videoInfo.duration.toFixed(2)}s\t${humanBytes(videoInfo.bytes)}`,
      `docs/media/word-demo.gif\t${gifInfo.width}x${gifInfo.height}\t${gifInfo.duration.toFixed(2)}s\t${humanBytes(gifInfo.bytes)}`
    ];
    console.log(rows.join('\n'));
  } finally {
    try {
      if (browser) await browser.close();
    } finally {
      try {
        if (server) await stopFixtureServer(server);
      } finally {
        rmSync(ARTIFACTS, { recursive: true, force: true });
      }
    }
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
