// 用法: node tools/shot.mjs [file] [out.png] [waitMs]
import { spawn } from 'node:child_process';
import { writeFileSync } from 'node:fs';
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const file = process.argv[2] || 'file:///D:/mypy/speech-lab/tone-anim/index.html';
const out = process.argv[3] || 'D:/mypy/speech-lab/tone-anim/tools/shot.png';
const full = /full/.test(out);
const wait = parseInt(process.argv[4] || '2600', 10);
const port = 9400 + Math.floor(Math.random() * 300);
const profile = 'D:/mypy/speech-lab/tone-anim/tools/.cdp-' + port;
const url = /^https?:|^file:/.test(file) ? file : 'file:///' + file.replace(/\\/g, '/');
const chrome = spawn(CHROME, ['--headless=new','--no-sandbox','--disable-gpu','--hide-scrollbars','--force-device-scale-factor=1','--window-size=1280,2000','--remote-debugging-port='+port,'--user-data-dir='+profile,'--no-first-run','--remote-allow-origins=*', url], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let ws;
try {
  let targets;
  for (let i = 0; i < 80; i++) {
    try { const resp = await fetch('http://127.0.0.1:'+port+'/json/list'); targets = await resp.json(); if (targets.some(t=>t.type==='page')) break; } catch {}
    await sleep(250);
  }
  if (!targets) throw new Error('no chrome target');
  const page = targets.find(t=>t.type==='page');
  ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0; const pend = new Map();
  const send = (method, params) => new Promise((res, rej) => { const i = ++id; pend.set(i,{res,rej}); ws.send(JSON.stringify({id:i,method,params:params||{}})); });
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { pend.get(m.id).res(m.result); pend.delete(m.id); } };
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width:1280, height:900, deviceScaleFactor:1, mobile:false });
  await sleep(wait);
  const err = await send('Runtime.evaluate', { expression: 'window.__errs && window.__errs.length ? window.__errs.join(" | ") : "(no js errors)"', returnByValue: true });
  const shotR = await send('Page.captureScreenshot', { format:'png', captureBeyondViewport:full, fromSurface:true });
  if (shotR && shotR.data) writeFileSync(out, Buffer.from(shotR.data, 'base64'));
  console.log('SHOT_OK ' + out);
  console.log('JSERR ' + (err && err.result ? err.result.value : 'n/a'));
} catch (e) {
  console.error('FAILED ' + e.message);
} finally {
  if (ws) { try { ws.close(); } catch {} }
  chrome.kill();
  setTimeout(()=>process.exit(0), 300);
}
