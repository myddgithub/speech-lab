// 用法: node tools/shot.mjs [file] [out.png] [waitMs]   （与仓库其他项目同款自测工具）
import { spawn } from 'node:child_process';
import { writeFileSync } from 'node:fs';
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const BASE = 'D:/mypy/speech-lab/music-acoustics-anim';
const file = process.argv[2] || 'file:///' + BASE + '/index.html';
const out = process.argv[3] || BASE + '/tools/shot.png';
const full = /full/.test(out);
const wait = parseInt(process.argv[4] || '3200', 10);
const port = 9400 + Math.floor(Math.random() * 300);
const profile = BASE + '/tools/.cdp-' + port;
const chrome = spawn(CHROME, ['--headless=new','--no-sandbox','--disable-gpu','--hide-scrollbars','--force-device-scale-factor=1','--window-size=1280,2200','--remote-debugging-port='+port,'--user-data-dir='+profile,'--no-first-run','--remote-allow-origins=*', file], { stdio: 'ignore' });
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
  await send('Emulation.setDeviceMetricsOverride', { width:1280, height:1000, deviceScaleFactor:1, mobile:false });
  await sleep(wait);
  const r1 = await send('Runtime.evaluate', { expression: 'JSON.stringify({errs:window.__errs||[],boot:window.__boot,fr:window.__frames})', returnByValue: true });
  console.log('STATE ' + (r1 && r1.result ? r1.result.value : 'n/a'));
  const shotR = await send('Page.captureScreenshot', { format:'png', captureBeyondViewport:full, fromSurface:true });
  if (shotR && shotR.data) writeFileSync(out, Buffer.from(shotR.data, 'base64'));
  console.log('SHOT_OK ' + out);
} catch (e) {
  console.error('FAILED ' + e.message);
} finally {
  if (ws) { try { ws.close(); } catch {} }
  chrome.kill();
  setTimeout(()=>process.exit(0), 300);
}
