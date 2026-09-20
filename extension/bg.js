/**
 * bg.js - Manifest V3 service worker.
 *
 * Nhiem vu: dieu phoi (khong tu lam audio).
 *   popup --START--> bg: lay streamId cua tab dang active (chrome.tabCapture.getMediaStreamId)
 *                        -> tao offscreen document -> gui OFFSCREEN_START
 *   offscreen: getUserMedia(tab) -> PCM int16 16kHz -> WebSocket /ws/stream
 *   popup --STOP--> bg: gui OFFSCREEN_STOP (offscreen gui frame rong 0 byte roi dong WS)
 *                        -> chrome.offscreen.closeDocument()
 *
 * Ly do phai co offscreen document: MV3 service worker KHONG co DOM/MediaStream,
 * nen khong the tu tieu thu stream tu chrome.tabCapture.
 *
 * Moi message noi bo deu co truong "target": 'bg' | 'offscreen' | 'popup'.
 */

const OFFSCREEN_PATH = 'offscreen.html';
const DEFAULT_BASE = 'http://localhost:8000';
const LOG_MAX = 30;
const PREF_DEFAULT = { base: DEFAULT_BASE, mode: 'translate', pin: '' };

// ---------------------------------------------------------------- state

let state = {
  running: false,
  sid: '',
  link: '',
  base: DEFAULT_BASE,
  mode: 'translate',
  pin: '',
  tabId: null,
  startedAt: 0,
  lastStatus: '',
  lastMsg: '',
  log: []
};

// storage.session: song sot qua cac lan service worker bi Chrome tat (trong cung phien browser).
const stateReady = (async () => {
  try {
    const got = await chrome.storage.session.get('state');
    if (got && got.state && typeof got.state === 'object') {
      state = Object.assign(state, got.state);
      if (!Array.isArray(state.log)) state.log = [];
    }
  } catch (e) {
    /* storage.session khong co -> chi dung bien module */
  }
})();

function persist() {
  try {
    chrome.storage.session.set({ state }).catch(() => {});
  } catch (e) {
    /* ignore */
  }
}

function publicState() {
  return {
    running: state.running,
    sid: state.sid,
    link: state.link,
    base: state.base,
    mode: state.mode,
    pin: state.pin,
    startedAt: state.startedAt,
    lastStatus: state.lastStatus,
    lastMsg: state.lastMsg,
    log: state.log.slice(-LOG_MAX)
  };
}

function pushLog(kind, text) {
  state.log.push({ t: Date.now(), kind: String(kind || 'info'), text: String(text == null ? '' : text) });
  if (state.log.length > LOG_MAX) state.log = state.log.slice(-LOG_MAX);
}

/** Gui message toi popup (neu popup dang mo). Popup dong -> loi la binh thuong. */
function broadcast(msg) {
  try {
    chrome.runtime.sendMessage(msg).catch(() => {});
  } catch (e) {
    /* ignore */
  }
}

function pushState() {
  broadcast({ target: 'popup', type: 'STATE', state: publicState() });
}

// ---------------------------------------------------------------- helpers

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function errText(e) {
  return String((e && e.message) || e || 'loi khong ro');
}

function withTimeout(promise, ms, label) {
  let timer = null;
  return Promise.race([
    Promise.resolve(promise).finally(() => { if (timer) clearTimeout(timer); }),
    new Promise((_, rej) => {
      timer = setTimeout(() => rej(new Error(label || 'timeout')), ms);
    })
  ]);
}

/** 'localhost:8000' -> 'http://localhost:8000' ; bo '/' cuoi. */
function normalizeBase(raw) {
  let b = String(raw == null ? '' : raw).trim();
  if (!b) b = DEFAULT_BASE;
  if (!/^https?:\/\//i.test(b)) b = 'http://' + b;
  return b.replace(/\/+$/, '');
}

function wsBase(httpBase) {
  return normalizeBase(httpBase).replace(/^http/i, 'ws');
}

// ---------------------------------------------------------------- offscreen lifecycle

let offscreenCreating = null;

async function offscreenAlive() {
  try {
    if (chrome.offscreen && typeof chrome.offscreen.hasDocument === 'function') {
      return await chrome.offscreen.hasDocument();
    }
  } catch (e) {
    /* Chrome cu -> coi nhu chua biet */
  }
  return false;
}

/** Tao offscreen document. Idempotent: "Only a single offscreen document may be created". */
function ensureOffscreen() {
  if (!offscreenCreating) {
    offscreenCreating = (async () => {
      if (await offscreenAlive()) return;
      try {
        await chrome.offscreen.createDocument({
          url: OFFSCREEN_PATH,
          reasons: ['USER_MEDIA'],
          justification: 'Capture tab audio and stream 16kHz PCM to the local EN-VI translation backend.'
        });
      } catch (e) {
        const m = errText(e);
        // Da ton tai -> coi nhu thanh cong (idempotent)
        if (!/single offscreen|already exists|Only a single/i.test(m)) throw e;
      }
    })();
    offscreenCreating = offscreenCreating.then(
      () => { offscreenCreating = null; },
      (e) => { offscreenCreating = null; throw e; }
    );
  }
  return offscreenCreating;
}

async function closeOffscreen() {
  try {
    if (await offscreenAlive()) await chrome.offscreen.closeDocument();
  } catch (e) {
    pushLog('warn', 'closeDocument: ' + errText(e));
  }
}

/**
 * Gui message toi offscreen document. Ngay sau createDocument(), listener cua
 * offscreen co the chua kip dang ky -> retry vai lan.
 */
async function sendToOffscreen(msg, timeoutMs) {
  const full = Object.assign({ target: 'offscreen' }, msg);
  let lastErr = null;
  for (let i = 0; i < 12; i++) {
    try {
      const reply = await withTimeout(chrome.runtime.sendMessage(full), timeoutMs || 8000, 'offscreen timeout');
      return reply;
    } catch (e) {
      lastErr = e;
      const m = errText(e);
      // CHI retry khi listener cua offscreen chua kip dang ky.
      // Timeout / loi khac -> nem ra ngay (retry se bat capture 2 lan).
      if (!/Receiving end does not exist|message port closed|Could not establish connection/i.test(m)) throw e;
      await sleep(150);
    }
  }
  throw lastErr || new Error('Khong ket noi duoc offscreen document.');
}

// ---------------------------------------------------------------- server API

async function apiCreateSession(base, opts) {
  const body = new URLSearchParams();
  body.set('topic', opts.topic || 'Tab audio');
  body.set('host', base);
  body.set('pin', opts.pin || '');
  if (opts.mode) body.set('mode', opts.mode);
  const res = await fetch(base + '/session/create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString()
  });
  if (!res.ok) throw new Error('POST /session/create -> HTTP ' + res.status);
  return await res.json();
}

async function apiHealth(base) {
  const res = await fetch(base + '/health', { method: 'GET' });
  if (!res.ok) throw new Error('GET /health -> HTTP ' + res.status);
  return await res.json();
}

// ---------------------------------------------------------------- commands

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return (tabs && tabs[0]) || null;
}

async function cmdStart(msg) {
  await stateReady;

  const base = normalizeBase(msg.base || state.base || PREF_DEFAULT.base);
  const mode = msg.mode === 'transcribe' ? 'transcribe' : 'translate';
  const pin = String(msg.pin || '');
  state.base = base;
  state.mode = mode;
  state.pin = pin;
  try { await chrome.storage.local.set({ base, mode, pin }); } catch (e) { /* ignore */ }

  if (state.running && (await offscreenAlive())) {
    return { ok: false, error: 'Dang chay. Bam "Dung" truoc khi bat lai.' };
  }

  const tab = await getActiveTab();
  if (!tab || tab.id == null) throw new Error('Khong tim thay tab dang mo.');

  // 1) Phong (session) - tao moi neu chua co
  let sid = msg.sid || state.sid || '';
  let link = state.link || '';
  if (!sid) {
    const created = await apiCreateSession(base, { topic: tab.title || 'Tab audio', pin, mode });
    sid = String(created.sid || '');
    link = String(created.link || '');
    if (!sid) throw new Error('Server khong tra ve sid.');
    pushLog('session', 'Tao phong moi: ' + sid);
  }
  if (!link) link = base + '/room/' + sid;

  // 2) streamId cua tab (PHAI goi tu service worker, va phai dung ngay)
  let streamId;
  try {
    streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id });
  } catch (e) {
    throw new Error('tabCapture.getMediaStreamId: ' + errText(e) +
      ' (khong bat duoc tab chrome://, Chrome Web Store, hoac tab dang bi app khac chiem audio)');
  }

  // 3) offscreen document
  await ensureOffscreen();

  // 4) bat dau trong offscreen
  const reply = await sendToOffscreen({
    type: 'OFFSCREEN_START',
    streamId,
    base,
    sid,
    mode,
    pin
  }, 20000);
  if (!reply || !reply.ok) {
    await closeOffscreen();
    throw new Error((reply && reply.error) || 'Offscreen khong khoi dong duoc.');
  }

  state.running = true;
  state.sid = sid;
  state.link = link;
  state.tabId = tab.id;
  state.startedAt = Date.now();
  state.lastStatus = 'starting';
  state.lastMsg = 'Dang bat audio tab...';
  pushLog('info', 'BAT DAU - tab: ' + (tab.title || tab.id) + ' [' + mode + ']');
  persist();
  pushState();
  return { ok: true, state: publicState() };
}

async function cmdStop() {
  await stateReady;
  if (await offscreenAlive()) {
    try {
      await sendToOffscreen({ type: 'OFFSCREEN_STOP' }, 8000);
    } catch (e) {
      pushLog('warn', 'OFFSCREEN_STOP: ' + errText(e));
    }
  }
  await closeOffscreen();
  state.running = false;
  state.tabId = null;
  state.startedAt = 0;
  state.lastStatus = 'stopped';
  state.lastMsg = 'Da dung.';
  pushLog('info', 'DUNG - da gui frame rong (chot cau cuoi) va dong phien.');
  persist();
  pushState();
  return { ok: true, state: publicState() };
}

async function cmdCreateSession(msg) {
  await stateReady;
  const base = normalizeBase(msg.base || state.base);
  const pin = String(msg.pin || '');
  const mode = msg.mode === 'transcribe' ? 'transcribe' : 'translate';
  const tab = await getActiveTab();
  const created = await apiCreateSession(base, {
    topic: (tab && tab.title) || 'Tab audio',
    pin,
    mode
  });
  state.base = base;
  state.mode = mode;
  state.pin = pin;
  state.sid = String(created.sid || '');
  state.link = String(created.link || (base + '/room/' + created.sid));
  pushLog('session', 'Tao phong moi: ' + state.sid + ' | locked=' + !!created.locked);
  persist();
  pushState();
  return { ok: true, sid: state.sid, link: state.link, qr: created.qr || '', locked: !!created.locked, state: publicState() };
}

async function cmdHealth(msg) {
  await stateReady;
  const base = normalizeBase(msg.base || state.base);
  const h = await apiHealth(base);
  pushLog('server', 'health: loaded=' + !!h.loaded + ' loading=' + !!h.loading + ' offline=' + !!h.offline);
  return { ok: true, health: h };
}

async function cmdOpenRoom(msg) {
  await stateReady;
  const url = String(msg.link || state.link || '');
  if (!url) throw new Error('Chua co link phong. Bam "Tao phong moi" truoc.');
  await chrome.tabs.create({ url });
  pushLog('info', 'Mo trang phong: ' + url);
  persist();
  return { ok: true, url };
}

async function cmdGetState() {
  await stateReady;
  const alive = await offscreenAlive();
  // offscreen document khong con -> capture da chet (vd tab bi dong)
  if (state.running && !alive) {
    state.running = false;
    state.lastStatus = 'stopped';
    state.lastMsg = 'Phien da ket thuc.';
    pushLog('warn', 'Offscreen document khong con -> danh dau da dung.');
    persist();
  }
  return { ok: true, state: publicState() };
}

/** Su kien tu offscreen document -> luu log + phat lai cho popup. */
function onOffscreenEvent(ev) {
  if (!ev || typeof ev !== 'object') return;
  const t = ev.type;
  if (t === 'status') {
    state.lastStatus = ev.status || '';
    state.lastMsg = ev.msg || '';
    pushLog('server', '[' + (ev.status || '?') + '] ' + (ev.msg || ''));
  } else if (t === 'partial') {
    pushLog('partial', String(ev.en || '') + (ev.vi ? '  =>  ' + ev.vi : ''));
  } else if (t === 'final') {
    pushLog('final', (ev.speaker ? ev.speaker + ': ' : '') + String(ev.en || '') + (ev.vi ? '  =>  ' + ev.vi : ''));
  } else if (t === 'error') {
    state.lastStatus = 'error';
    state.lastMsg = ev.msg || 'loi';
    pushLog('error', state.lastMsg);
  } else if (t === 'ws') {
    pushLog('ws', 'WS ' + (ev.state || '') + (ev.msg ? ' (' + ev.msg + ')' : ''));
  } else if (t === 'info') {
    pushLog('info', ev.msg || '');
  } else if (t === 'stopped') {
    state.running = false;
    state.tabId = null;
    state.startedAt = 0;
    pushLog('info', 'Offscreen da dung va giai phong audio.');
  } else {
    pushLog('info', 'event: ' + t);
  }
  persist();
  broadcast({ target: 'popup', type: 'EVENT', event: ev, state: publicState() });
}

// ---------------------------------------------------------------- message router

const COMMANDS = {
  START: cmdStart,
  STOP: cmdStop,
  CREATE_SESSION: cmdCreateSession,
  HEALTH: cmdHealth,
  OPEN_ROOM: cmdOpenRoom,
  GET_STATE: cmdGetState
};

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || typeof msg !== 'object') return;

  // Chi nhan message danh cho service worker (bo qua broadcast cho popup/offscreen).
  if (msg.target && msg.target !== 'bg') return;

  // Su kien tu offscreen: tra loi ngay (khong giu channel).
  if (msg.type === 'OFFSCREEN_EVENT') {
    onOffscreenEvent(msg.event);
    sendResponse({ ok: true });
    return;
  }

  const fn = COMMANDS[msg.type];
  if (!fn) {
    sendResponse({ ok: false, error: 'unknown message type: ' + msg.type });
    return;
  }

  // Tra loi BAT DONG BO -> phai return true.
  (async () => {
    try {
      const r = await fn(msg);
      sendResponse(r || { ok: true });
    } catch (e) {
      const text = errText(e);
      pushLog('error', text);
      persist();
      pushState();
      sendResponse({ ok: false, error: text });
    }
  })();
  return true;
});

// Neu tab dang duoc bat bi dong -> dung phien (khong can permission "tabs").
chrome.tabs.onRemoved.addListener((tabId) => {
  if (state.running && state.tabId === tabId) {
    pushLog('warn', 'Tab dang bat da bi dong -> tu dong dung.');
    cmdStop().catch(() => {});
  }
});

// Cap nhat / cai lai extension: don offscreen document cu cho sach.
chrome.runtime.onInstalled.addListener(() => {
  closeOffscreen();
});
