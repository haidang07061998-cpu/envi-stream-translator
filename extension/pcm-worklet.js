/**
 * pcm-worklet.js - AudioWorkletProcessor du phong.
 *
 * offscreen.js uu tien nap worklet tu Blob URL (khong can file nay). Nhung CSP cua
 * MV3 extension page mac dinh la "script-src 'self'", va mot so ban Chrome chan
 * blob: cho AudioWorklet.addModule. Khi do offscreen.js nap file nay qua
 * chrome.runtime.getURL('pcm-worklet.js') (same-origin, luon duoc 'self' cho phep),
 * truoc khi phai roi xuong createScriptProcessor.
 *
 * Nhiem vu: down-mix ve mono, gom 2048 mau roi postMessage (transferable) ve main thread.
 */
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
