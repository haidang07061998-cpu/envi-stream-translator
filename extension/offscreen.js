/**
 * offscreen.js - chay trong offscreen document (co DOM, khong co UI).
 *
 * Luong:
 *   getUserMedia({audio:{mandatory:{chromeMediaSource:'tab', chromeMediaSourceId}}})
 *     -> MediaStreamAudioSourceNode
 *          -> AudioContext.destination        (tra lai tieng cho nguoi dung: Chrome mute tab khi capture)
 *          -> AudioWorkletNode('pcm-tap')     (hoac createScriptProcessor neu worklet loi)
 *               -> down-mix mono -> resample 16 kHz (noi suy tuyen tinh)
 *               -> frame int16 little-endian 2048 mau -> WebSocket binary
 *
 * Server: WS /ws/stream?sid=&partial=1&mode=&pin=
 *   - frame rong (0 byte) = chot cau cuoi
 *   - JSON ve: {kind:'status'|'partial'|'final', ...}
 *
 * Moi su kien duoc bao ve bg.js qua chrome.runtime.sendMessage({target:'bg', type:'OFFSCREEN_EVENT'}).
 */

const TARGET_RATE = 16000;        // server yeu cau 16 kHz mono int16
const FRAME_SAMPLES = 2048;       // ~128 ms @16k
const RMS_GATE = 0.004;           // bo qua frame gan nhu im lang
const SILENCE_KEEPALIVE_MS = 2500; // nhung van gui 1 frame im lang moi 2.5s de server chot cau
const MAX_RECONNECT = 5;

const WORKLET_SRC = `
class PcmTapProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buf = new Float32Array(2048);
    this.n = 0;
  }
  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0 || !input[0]) return true;
    const nch = input.length;
    const len = input[0].length;
    for (let i = 0; i < len; i++) {
      let s = 0;
      for (let c = 0; c < nch; c++) s += input[c][i];
      this.buf[this.n++] = nch > 1 ? s / nch : s;
      if (this.n >= this.buf.length) {
        const out = this.buf.slice(0, this.n);
        this.port.postMessage(out, [out.buffer]);
        this.n = 0;
      }
    }
    return true;
  }
}
registerProcessor('pcm-tap', PcmTapProcessor);
`;

// ---------------------------------------------------------------- runtime state

let cfg = null;              // {streamId, base, sid, mode, pin}
let running = false;
let stopping = false;

let mediaStream = null;
let audioCtx = null;
let srcNode = null;
let workletNode = null;
let procNode = null;
let sinkGain = null;
let usingWorklet = false;

let ws = null;
let reconnectTimer = null;
let reconnectAttempts = 0;

// accumulator frame int16
const frame = new Int16Array(FRAME_SAMPLES);
let frameLen = 0;
let lastSentAt = 0;

// resampler (noi suy tuyen tinh)
const rs = { inRate: 48000, outRate: TARGET_RATE, buf: new Float32Array(0), pos: 0 };

// ---------------------------------------------------------------- helpers

function errText(e) {
  return String((e && e.message) || e || 'loi khong ro');
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function report(event) {
  try {
    chrome.runtime.sendMessage({ target: 'bg', type: 'OFFSCREEN_EVENT', event }).catch(() => {});
  } catch (e) {
    /* service worker dang ngu / khong co listener -> bo qua */
  }
}

function logInfo(msg) {
  report({ type: 'info', msg: String(msg) });
}

function normalizeBase(raw) {
  let b = String(raw == null ? '' : raw).trim();
  if (!b) b = 'http://localhost:8000';
  if (!/^https?:\/\//i.test(b)) b = 'http://' + b;
  return b.replace(/\/+$/, '');
}

function wsUrlFor(base, sid, mode, pin) {
  const u = normalizeBase(base).replace(/^http/i, 'ws') + '/ws/stream';
  const q = new URLSearchParams();
  q.set('sid', sid || '');
  q.set('partial', '1');
  q.set('mode', mode === 'transcribe' ? 'transcribe' : 'translate');
  if (pin) q.set('pin', pin);
  return u + '?' + q.toString();
}

// ---------------------------------------------------------------- resample + frame

function resetPipeline() {
  rs.buf = new Float32Array(0);
  rs.pos = 0;
  frameLen = 0;
  lastSentAt = 0;
}

/** Nhan mau mono o rs.inRate -> noi suy tuyen tinh -> 16 kHz -> gom frame 2048 mau. */
function pushSamples(samples) {
  if (!running || !samples || samples.length === 0) return;

  // Ghep phan du con lai voi chunk moi (chi copy vai nghin mau/lan -> re)
  const start = Math.floor(rs.pos);
  const tail = rs.buf.subarray(start);
  const merged = new Float32Array(tail.length + samples.length);
  merged.set(tail, 0);
  merged.set(samples, tail.length);
  rs.buf = merged;
  rs.pos -= start;

  const ratio = rs.inRate / rs.outRate;
  const usable = rs.buf.length - 1 - rs.pos;
  if (usable <= 0) return;
  const n = Math.ceil(usable / ratio);
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const p = rs.pos + i * ratio;
    const i0 = Math.floor(p);
    const f = p - i0;
    const a = rs.buf[i0];
    const b = i0 + 1 < rs.buf.length ? rs.buf[i0 + 1] : a;
    out[i] = a + (b - a) * f;
  }
  rs.pos += n * ratio;

  // cat bot phan da dung
  const cut = Math.floor(rs.pos);
  if (cut > 8192) {
    rs.buf = rs.buf.slice(cut);
    rs.pos -= cut;
  }

  for (let i = 0; i < out.length; i++) {
    const v = out[i] < -1 ? -1 : (out[i] > 1 ? 1 : out[i]);
    frame[frameLen++] = v < 0 ? (v * 0x8000) | 0 : (v * 0x7fff) | 0;
    if (frameLen >= FRAME_SAMPLES) sendFrame();
  }
}

function sendFrame() {
  if (frameLen < FRAME_SAMPLES) return;
  frameLen = 0;
  if (!ws || ws.readyState !== WebSocket.OPEN) return; // dang reconnect -> bo frame

  let sum = 0;
  for (let i = 0; i < FRAME_SAMPLES; i++) {
    const v = frame[i] / 32768;
    sum += v * v;
  }
  const rms = Math.sqrt(sum / FRAME_SAMPLES);
  const now = Date.now();

  // Gate im lang, nhung van "keepalive" 1 frame im lang de server tu chot cau.
  if (rms < RMS_GATE && now - lastSentAt < SILENCE_KEEPALIVE_MS) return;

  try {
    ws.send(frame.slice().buffer); // int16 LE, mono, 16 kHz, 4096 byte
    lastSentAt = now;
  } catch (e) {
    report({ type: 'error', msg: 'ws.send: ' + errText(e) });
  }
}

// ---------------------------------------------------------------- websocket

function onServerMessage(data) {
  if (typeof data !== 'string') return;
  let m = null;
  try { m = JSON.parse(data); } catch (e) { return; }
  if (!m || !m.kind) return;
  if (m.kind === 'status') {
    report({ type: 'status', status: m.status || '', msg: m.msg || '' });
  } else if (m.kind === 'partial') {
    report({ type: 'partial', en: m.en || '', vi: m.vi == null ? null : m.vi });
  } else if (m.kind === 'final') {
    report({ type: 'final', en: m.en || '', vi: m.vi == null ? null : m.vi, speaker: m.speaker || '' });
  } else {
    logInfo('server kind=' + m.kind);
  }
}

function openSocket() {
  if (!running || stopping || !cfg) return;
  let url;
  try {
    url = wsUrlFor(cfg.base, cfg.sid, cfg.mode, cfg.pin);
  } catch (e) {
    report({ type: 'error', msg: 'URL WS khong hop le: ' + errText(e) });
    return;
  }

  report({ type: 'ws', state: 'connecting', msg: url });
  let sock;
  try {
    sock = new WebSocket(url);
  } catch (e) {
    report({ type: 'error', msg: 'Khong mo duoc WebSocket: ' + errText(e) });
    return;
  }
  sock.binaryType = 'arraybuffer';
  ws = sock;

  sock.onopen = () => {
    reconnectAttempts = 0;
    report({ type: 'ws', state: 'open', msg: 'da ket noi ' + url });
  };
  sock.onmessage = (ev) => {
    if (typeof ev.data === 'string') onServerMessage(ev.data);
    else if (ev.data instanceof ArrayBuffer) {
      try { onServerMessage(new TextDecoder().decode(ev.data)); } catch (e) { /* ignore */ }
    }
  };
  sock.onerror = () => {
    report({ type: 'ws', state: 'error', msg: 'loi socket (kiem tra server da chay chua)' });
  };
  sock.onclose = (ev) => {
    if (ws === sock) ws = null;
    if (stopping || !running) return;
    report({ type: 'ws', state: 'closed', msg: 'code=' + ev.code });
    scheduleReconnect('closed code=' + ev.code);
  };
}

function scheduleReconnect(reason) {
  if (!running || stopping) return;
  if (reconnectAttempts >= MAX_RECONNECT) {
    report({
      type: 'error',
      msg: 'Mat ket noi WebSocket sau ' + MAX_RECONNECT + ' lan thu. Da dung bat audio.'
    });
    stop().catch(() => {});
    return;
  }
  reconnectAttempts++;
  const delay = Math.min(8000, 500 * Math.pow(2, reconnectAttempts - 1));
  report({
    type: 'ws',
    state: 'reconnecting',
    msg: 'lan ' + reconnectAttempts + '/' + MAX_RECONNECT + ' sau ' + delay + 'ms (' + reason + ')'
  });
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    if (running && !stopping) openSocket();
  }, delay);
}

// ---------------------------------------------------------------- audio graph

/** Uu tien AudioWorklet (Blob URL -> file dong goi), cuoi cung moi createScriptProcessor. */
async function buildProcessor() {
  const ctx = audioCtx;
  if (ctx.audioWorklet && typeof ctx.audioWorklet.addModule === 'function') {
    // 1) Worklet inline qua Blob URL
    try {
      const url = URL.createObjectURL(new Blob([WORKLET_SRC], { type: 'application/javascript' }));
      try {
        await ctx.audioWorklet.addModule(url);
      } finally {
        URL.revokeObjectURL(url);
      }
      const node = new AudioWorkletNode(ctx, 'pcm-tap', {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        outputChannelCount: [1]
      });
      node.port.onmessage = (ev) => {
        const d = ev.data;
        if (d && d.length) pushSamples(d);
      };
      usingWorklet = true;
      logInfo('AudioWorklet: nap module tu Blob URL OK.');
      return node;
    } catch (e) {
      logInfo('AudioWorklet Blob URL loi (' + errText(e) + ') -> thu file dong goi.');
    }
    // 2) Worklet tu file trong extension (CSP 'self')
    try {
      await ctx.audioWorklet.addModule(chrome.runtime.getURL('pcm-worklet.js'));
      const node = new AudioWorkletNode(ctx, 'pcm-tap', {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        outputChannelCount: [1]
      });
      node.port.onmessage = (ev) => {
        const d = ev.data;
        if (d && d.length) pushSamples(d);
      };
      usingWorklet = true;
      logInfo('AudioWorklet: nap pcm-worklet.js OK.');
      return node;
    } catch (e) {
      logInfo('AudioWorklet file loi (' + errText(e) + ') -> dung createScriptProcessor.');
    }
  }

  // 3) Fallback: ScriptProcessor (deprecated nhung van chay)
  const node = ctx.createScriptProcessor(4096, 1, 1);
  node.onaudioprocess = (ev) => {
    const ch = ev.inputBuffer.getChannelData(0);
    pushSamples(new Float32Array(ch)); // copy: buffer cua he thong bi tai su dung
  };
  usingWorklet = false;
  return node;
}

function teardownAudio() {
  try { if (srcNode) srcNode.disconnect(); } catch (e) { /* ignore */ }
  try {
    if (workletNode) {
      workletNode.port.onmessage = null;
      workletNode.disconnect();
    }
  } catch (e) { /* ignore */ }
  try {
    if (procNode) {
      procNode.onaudioprocess = null;
      procNode.disconnect();
    }
  } catch (e) { /* ignore */ }
  try { if (sinkGain) sinkGain.disconnect(); } catch (e) { /* ignore */ }
  if (mediaStream) {
    mediaStream.getTracks().forEach((t) => {
      try { t.stop(); } catch (e) { /* ignore */ }
    });
  }
  if (audioCtx) {
    try { audioCtx.close(); } catch (e) { /* ignore */ }
  }
  mediaStream = null;
  audioCtx = null;
  srcNode = null;
  workletNode = null;
  procNode = null;
  sinkGain = null;
}

async function start(msg) {
  cfg = {
    streamId: msg.streamId,
    base: normalizeBase(msg.base),
    sid: String(msg.sid || ''),
    mode: msg.mode === 'transcribe' ? 'transcribe' : 'translate',
    pin: String(msg.pin || '')
  };
  if (!cfg.streamId) throw new Error('Thieu streamId (tabCapture).');
  if (!cfg.sid) throw new Error('Thieu sid (phong).');

  stopping = false;
  running = true;
  reconnectAttempts = 0;
  resetPipeline();

  // 1) Bat audio tab
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        mandatory: {
          chromeMediaSource: 'tab',
          chromeMediaSourceId: cfg.streamId
        }
      },
      video: false
    });
  } catch (e) {
    running = false;
    teardownAudio();
    throw new Error('getUserMedia(tab): ' + errText(e));
  }
  logInfo('Da bat audio tab (' + mediaStream.getAudioTracks().length + ' track).');

  // 2) AudioContext: vua de xu ly, vua de tra tieng lai cho nguoi dung
  try {
    audioCtx = new AudioContext();
  } catch (e) {
    running = false;
    teardownAudio();
    throw new Error('AudioContext: ' + errText(e));
  }
  rs.inRate = audioCtx.sampleRate || 48000;
  rs.outRate = TARGET_RATE;
  logInfo('AudioContext sampleRate=' + rs.inRate + ' -> resample ' + TARGET_RATE + ' Hz.');

  try {
    if (audioCtx.state === 'suspended') await audioCtx.resume();
  } catch (e) { /* ignore */ }
  if (audioCtx.state !== 'running') {
    // watchdog: offscreen document co the bi autoplay policy giu suspended
    let tries = 0;
    const wd = setInterval(async () => {
      tries++;
      if (!running || !audioCtx) { clearInterval(wd); return; }
      try { await audioCtx.resume(); } catch (e) { /* ignore */ }
      if (audioCtx.state === 'running' || tries > 20) {
        clearInterval(wd);
        report({ type: 'status', status: audioCtx.state === 'running' ? 'ready' : 'error',
                 msg: 'AudioContext state=' + audioCtx.state });
      }
    }, 500);
  }

  srcNode = audioCtx.createMediaStreamSource(mediaStream);

  // 3) QUAN TRONG: Chrome mute audio cua tab khi bi capture -> phat lai qua destination.
  //    Day la audio cua TAB (khong phai micro) nen khong gay vong lap/feedback.
  srcNode.connect(audioCtx.destination);

  // 4) Node xu ly -> gain 0 -> destination (de node duoc "keo" ma khong them tieng)
  sinkGain = audioCtx.createGain();
  sinkGain.gain.value = 0;
  sinkGain.connect(audioCtx.destination);

  try {
    const node = await buildProcessor();
    if (usingWorklet) workletNode = node; else procNode = node;
    srcNode.connect(node);
    node.connect(sinkGain);
  } catch (e) {
    running = false;
    teardownAudio();
    throw new Error('Khong tao duoc node xu ly audio: ' + errText(e));
  }

  // 5) WebSocket
  openSocket();

  report({
    type: 'ws',
    state: 'started',
    msg: 'dang gui PCM 16kHz mono | sid=' + cfg.sid + ' | mode=' + cfg.mode
  });
}

async function stop() {
  if (stopping) return;
  stopping = true;
  running = false;

  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  // Frame rong (0 byte) = yeu cau server chot cau cuoi truoc khi dong phien.
  try {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(new ArrayBuffer(0));
      await sleep(600); // cho server finalize + gui final
    }
  } catch (e) {
    report({ type: 'ws', state: 'error', msg: 'gui frame rong: ' + errText(e) });
  }

  try {
    if (ws) {
      ws.onclose = null;
      ws.onerror = null;
      ws.onmessage = null;
      ws.close();
    }
  } catch (e) { /* ignore */ }
  ws = null;

  teardownAudio();
  resetPipeline();

  stopping = false;
  report({ type: 'stopped' });
}

// ---------------------------------------------------------------- messages

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || typeof msg !== 'object' || msg.target !== 'offscreen') return;

  if (msg.type === 'OFFSCREEN_START') {
    (async () => {
      try {
        await start(msg);
        sendResponse({ ok: true });
      } catch (e) {
        const text = errText(e);
        report({ type: 'error', msg: text });
        sendResponse({ ok: false, error: text });
      }
    })();
    return true; // tra loi bat dong bo
  }

  if (msg.type === 'OFFSCREEN_STOP') {
    (async () => {
      try {
        await stop();
        sendResponse({ ok: true });
      } catch (e) {
        sendResponse({ ok: false, error: errText(e) });
      }
    })();
    return true;
  }

  if (msg.type === 'OFFSCREEN_PING') {
    sendResponse({
      ok: true,
      running,
      ctxState: audioCtx ? audioCtx.state : null,
      worklet: usingWorklet,
      ws: ws ? ws.readyState : null,
      sid: cfg ? cfg.sid : ''
    });
    return;
  }
});
