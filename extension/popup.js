/**
 * popup.js - UI dieu khien. Khong co inline script / inline onclick (CSP cua MV3 cam).
 * Moi lenh gui cho service worker duoi dang {target:'bg', type:...}.
 */

const $ = (id) => document.getElementById(id);
const LOG_MAX = 40;

const els = {
  base: $('base'),
  pin: $('pin'),
  mode: $('mode'),
  start: $('start'),
  stop: $('stop'),
  open: $('open'),
  create: $('create'),
  health: $('health'),
  link: $('link'),
  copy: $('copy'),
  pill: $('pill'),
  log: $('log'),
  healthLine: $('healthLine')
};

const DEFAULTS = { base: 'http://localhost:8000', mode: 'translate', pin: '' };

let lines = [];              // {kind, text} - log da chot
let live = { en: '', vi: '' }; // partial dang chay (hien o cuoi log)
let running = false;

// ---------------------------------------------------------------- helpers

function addLine(kind, text) {
  lines.push({ kind: kind || 'info', text: String(text == null ? '' : text) });
  if (lines.length > LOG_MAX) lines = lines.slice(-LOG_MAX);
  renderLog();
}

function renderLog() {
  const box = els.log;
  box.textContent = '';
  const all = lines.slice();
  if (live.en) all.push({ kind: 'en', text: 'EN~ ' + live.en });
  if (live.vi) all.push({ kind: 'vi', text: 'VI~ ' + live.vi });
  for (const l of all) {
    const d = document.createElement('div');
    d.className = 'l ' + l.kind;
    d.textContent = l.text;
    box.appendChild(d);
  }
  box.scrollTop = box.scrollHeight;
}

function setPill(text, cls) {
  els.pill.textContent = text;
  els.pill.className = 'pill' + (cls ? ' ' + cls : '');
}

function setRunning(on) {
  running = !!on;
  els.start.disabled = running;
  els.stop.disabled = !running;
}

function baseValue() {
  const v = els.base.value.trim();
  return v || DEFAULTS.base;
}

/** Gui lenh cho service worker. Luon resolve {ok:...}, khong nem ra ngoai. */
async function bg(type, extra) {
  try {
    const reply = await chrome.runtime.sendMessage(Object.assign({ target: 'bg', type }, extra || {}));
    return reply || { ok: false, error: 'khong co phan hoi tu service worker' };
  } catch (e) {
    return { ok: false, error: String((e && e.message) || e) };
  }
}

function applyState(st) {
  if (!st) return;
  if (typeof st.base === 'string' && st.base && !els.base.value) els.base.value = st.base;
  if (st.mode) els.mode.value = st.mode === 'transcribe' ? 'transcribe' : 'translate';
  if (typeof st.pin === 'string' && !els.pin.value) els.pin.value = st.pin;
  els.link.value = st.link || '';
  setRunning(!!st.running);
  if (st.running) setPill('DANG CHAY', 'on');
  else if (st.lastStatus === 'error') setPill('LOI', 'err');
  else setPill('chua chay', '');
  if (Array.isArray(st.log) && st.log.length && !lines.length) {
    lines = st.log.slice(-LOG_MAX).map((l) => ({ kind: l.kind || 'info', text: l.text || '' }));
    renderLog();
  }
}

function healthText(h) {
  if (!h) return '\u2014';
  const parts = [];
  parts.push(h.loaded ? 'model: san sang' : (h.loading ? 'model: dang tai' : 'model: chua tai'));
  if (h.offline) parts.push('offline=1');
  if (h.asr) parts.push('asr=' + h.asr);
  if (h.tts) parts.push('tts=' + h.tts);
  if (h.mode) parts.push('mode=' + h.mode);
  if (typeof h.glossary_terms === 'number') parts.push('glossary=' + h.glossary_terms);
  if (h.confidential) parts.push('confidential=1');
  if (h.error) parts.push('error=' + h.error);
  return parts.join(' \u00b7 ');
}

// ---------------------------------------------------------------- actions

async function onStart() {
  setPill('dang bat...', 'warn');
  els.start.disabled = true;
  const reply = await bg('START', {
    base: baseValue(),
    pin: els.pin.value,
    mode: els.mode.value
  });
  if (!reply.ok) {
    addLine('error', 'Khong bat duoc: ' + (reply.error || 'loi khong ro'));
    setPill('LOI', 'err');
    els.start.disabled = false;
    return;
  }
  if (reply.state) applyState(reply.state);
  addLine('info', 'Da bat tab. Xem log ben duoi de theo doi caption.');
}

async function onStop() {
  els.stop.disabled = true;
  const reply = await bg('STOP');
  if (!reply.ok) addLine('error', 'Dung loi: ' + (reply.error || 'loi khong ro'));
  else addLine('info', 'Da dung.');
  if (reply.state) applyState(reply.state);
  else setRunning(false);
}

async function onCreate() {
  const reply = await bg('CREATE_SESSION', {
    base: baseValue(),
    pin: els.pin.value,
    mode: els.mode.value
  });
  if (!reply.ok) {
    addLine('error', 'Tao phong loi: ' + (reply.error || 'loi khong ro'));
    return;
  }
  els.link.value = reply.link || '';
  addLine('session', 'Phong moi: ' + reply.sid + (reply.locked ? ' (co PIN)' : ''));
  addLine('session', reply.link || '');
}

async function onOpen() {
  const url = els.link.value.trim();
  if (!url) {
    addLine('warn', 'Chua co link phong. Bam "Tao phong moi" hoac "Bat dau dich tab nay" truoc.');
    return;
  }
  const reply = await bg('OPEN_ROOM', { link: url });
  if (!reply.ok) addLine('error', 'Mo phong loi: ' + (reply.error || 'loi khong ro'));
  else addLine('info', 'Da mo tab phong: ' + url);
}

async function onHealth() {
  els.health.disabled = true;
  els.healthLine.textContent = 'dang kiem tra...';
  const reply = await bg('HEALTH', { base: baseValue() });
  els.health.disabled = false;
  if (!reply.ok) {
    els.healthLine.textContent = 'Khong ket noi duoc ' + baseValue() + ' (' + (reply.error || '') + ')';
    addLine('error', 'health: ' + (reply.error || 'loi'));
    return;
  }
  els.healthLine.textContent = healthText(reply.health);
  addLine('server', 'health OK: ' + healthText(reply.health));
}

async function onCopy() {
  const text = els.link.value.trim();
  if (!text) {
    addLine('warn', 'Chua co link de copy.');
    return;
  }
  let ok = false;
  try {
    await navigator.clipboard.writeText(text);
    ok = true;
  } catch (e) {
    ok = false;
  }
  if (!ok) {
    try {
      els.link.removeAttribute('readonly');
      els.link.select();
      ok = document.execCommand('copy');
      els.link.setAttribute('readonly', 'readonly');
      window.getSelection().removeAllRanges();
    } catch (e) {
      ok = false;
    }
  }
  els.copy.textContent = ok ? 'Da copy' : 'Loi';
  setTimeout(() => { els.copy.textContent = 'Copy'; }, 1200);
}

// ---------------------------------------------------------------- events

els.start.addEventListener('click', () => { onStart(); });
els.stop.addEventListener('click', () => { onStop(); });
els.create.addEventListener('click', () => { onCreate(); });
els.open.addEventListener('click', () => { onOpen(); });
els.health.addEventListener('click', () => { onHealth(); });
els.copy.addEventListener('click', () => { onCopy(); });

function savePrefs() {
  try {
    chrome.storage.local.set({
      base: baseValue(),
      pin: els.pin.value,
      mode: els.mode.value
    }).catch(() => {});
  } catch (e) { /* ignore */ }
}
els.base.addEventListener('change', savePrefs);
els.pin.addEventListener('change', savePrefs);
els.mode.addEventListener('change', savePrefs);

// Su kien tu service worker (status/partial/final tu server, doi trang thai...)
chrome.runtime.onMessage.addListener((msg) => {
  if (!msg || msg.target !== 'popup') return;
  if (msg.type === 'STATE') {
    applyState(msg.state);
    return;
  }
  if (msg.type !== 'EVENT') return;

  const ev = msg.event || {};
  if (msg.state) applyState(msg.state);

  if (ev.type === 'status') {
    if (ev.status === 'ready') setPill('SAN SANG', 'on');
    else if (ev.status === 'error') setPill('LOI SERVER', 'err');
    else setPill('dang tai model', 'warn');
    addLine('server', '[' + (ev.status || '?') + '] ' + (ev.msg || ''));
  } else if (ev.type === 'partial') {
    live.en = ev.en || '';
    live.vi = ev.vi || '';
    renderLog();
  } else if (ev.type === 'final') {
    live.en = '';
    live.vi = '';
    addLine('en', 'EN ' + (ev.speaker ? ev.speaker + ': ' : '') + (ev.en || ''));
    if (ev.vi) addLine('vi', 'VI ' + ev.vi);
  } else if (ev.type === 'error') {
    addLine('error', ev.msg || 'loi');
    setPill('LOI', 'err');
  } else if (ev.type === 'ws') {
    addLine('ws', 'WS ' + (ev.state || '') + (ev.msg ? ' \u00b7 ' + ev.msg : ''));
    if (ev.state === 'started') setPill('DANG CHAY', 'on');
  } else if (ev.type === 'info') {
    addLine('info', ev.msg || '');
  } else if (ev.type === 'stopped') {
    live.en = '';
    live.vi = '';
    setRunning(false);
    setPill('da dung', '');
    renderLog();
  }
});

// ---------------------------------------------------------------- init

(async function init() {
  try {
    const saved = await chrome.storage.local.get(Object.keys(DEFAULTS));
    els.base.value = saved.base || DEFAULTS.base;
    els.mode.value = saved.mode === 'transcribe' ? 'transcribe' : 'translate';
    els.pin.value = saved.pin || '';
  } catch (e) {
    els.base.value = DEFAULTS.base;
  }
  renderLog();
  setRunning(false);

  const reply = await bg('GET_STATE');
  if (reply.ok && reply.state) applyState(reply.state);
  else if (!reply.ok) addLine('warn', 'Service worker: ' + (reply.error || 'khong phan hoi'));
  setPill(running ? 'DANG CHAY' : 'chua chay', running ? 'on' : '');
})();
