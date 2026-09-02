// 用法: node tools/shot.mjs [url] [evalExpr] [waitMs]
// 通过 CDP Runtime.evaluate 在页面内执行表达式并打印返回值（无截图，稳定）
import { spawn } from 'node:child_process';
import { readFileSync, rmSync } from 'node:fs';
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const url = process.argv[2] || 'file:///D:/mypy/shengmu-anim/index.html';
const exprArg = process.argv[3] || 'document.title';
const expr = exprArg.startsWith('@') ? readFileSync(exprArg.slice(1), 'utf8') : exprArg;
const wait = parseInt(process.argv[4] || '3500');
const port = 9400 + Math.floor(Math.random() * 300);
const profile = 'D:/mypy/shengmu-anim/tools/.cdp-' + port;
const chrome = spawn(CHROME, [
  '--headless=new', '--no-sandbox', '--disable-gpu',
  '--remote-debugging-port=' + port,
  '--user-data-dir=' + profile,
  '--no-first-run', '--no-default-browser-check', '--remote-allow-origins=*',
  url,
], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let targets;
for (let i = 0; i < 60; i++) {
  try {
    const r = await fetch('http://127.0.0.1:' + port + '/json/list');
    targets = await r.json();
    if (targets.some(t => t.type === 'page')) break;
  } catch {}
  await sleep(250);
}
if (!targets || !targets.some(t => t.type === 'page')) { console.error('no page target'); chrome.kill(); process.exit(1); }
const page = targets.find(t => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
let id = 0; const pending = new Map();
const send = (method, params) => new Promise((res, rej) => {
  const i = ++id; pending.set(i, { res, rej });
  ws.send(JSON.stringify({ id: i, method, params: params || {} }));
});
ws.onmessage = e => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id).res(m.result); pending.delete(m.id); }
};
const opened = new Promise((res, rej) => {
  const tmo = setTimeout(() => rej(new Error('ws timeout')), 8000);
  ws.onopen = () => { clearTimeout(tmo); res(); };
  ws.onerror = () => { clearTimeout(tmo); rej(new Error('ws error')); };
});
let exitCode = 0;
try {
  await opened;
  await send('Runtime.enable');
  await sleep(wait);
  const ev = await send('Runtime.evaluate', { expression: expr, returnByValue: true });
  const val = ev && ev.result ? ev.result.value : JSON.stringify(ev);
  if (ev && ev.exceptionDetails) { console.error('EXC: ' + (ev.exceptionDetails.exception ? ev.exceptionDetails.exception.description || JSON.stringify(ev.exceptionDetails.exception) : ev.exceptionDetails.text)); }
  console.log(String(val));
} catch (e) {
  console.error('FAILED: ' + e.message);
  exitCode = 2;
} finally {
  chrome.kill();
  if (chrome.exitCode === null) {
    await Promise.race([
      new Promise(resolve => chrome.once('exit', resolve)),
      sleep(1200),
    ]);
  }
  try { rmSync(profile, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 }); } catch {}
  setTimeout(() => process.exit(exitCode), 400);
}
