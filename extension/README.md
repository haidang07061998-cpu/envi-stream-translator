# Extension Chrome - EN-VI Tab Translator (live caption)

Bat audio cua **tab dang mo** (Google Meet / Zoom web / Microsoft Teams web / YouTube),
gui PCM 16 kHz mono ve backend local, va hien caption EN→VI tren trang phong.

## Cai dat

1. Chay backend: `uvicorn app.server:app --port 8000` (hoac `python -m app.server`) — doi model tai xong (`GET /health` -> `loaded: true`).
2. Chrome -> `chrome://extensions` -> bat **Developer mode** -> **Load unpacked** -> chon thu muc `extension/`.
3. Mo tab hop (Meet/Zoom/Teams/YouTube), bam icon extension.

## Cach dung

| Nut | Viec no lam |
|---|---|
| **Bat dau dich tab nay** | `POST /session/create` (neu chua co phong) -> `chrome.tabCapture.getMediaStreamId` -> tao offscreen document -> bat audio tab -> mo WS `/ws/stream` |
| **Dung** | Gui 1 frame rong (0 byte) de server chot cau cuoi -> dong WS -> `chrome.offscreen.closeDocument()` |
| **Mo trang phong** | Mo `link` (`/room/{sid}`) trong tab moi - noi nguoi nghe xem caption |
| **Tao phong moi** | Tao session moi (topic = tieu de tab, co PIN neu dien) |
| **Kiem tra server** | `GET /health` -> hien `loaded/loading/offline/asr/tts` |

Server URL (mac dinh `http://localhost:8000`), PIN va che do duoc luu trong `chrome.storage.local`.

## Luong ky thuat

```
popup.js  --{target:'bg', type:'START'}-->  bg.js (service worker)
                                              |  chrome.tabCapture.getMediaStreamId({targetTabId})
                                              |  chrome.offscreen.createDocument({url:'offscreen.html', reasons:['USER_MEDIA']})
                                              v
                                           offscreen.js  (co DOM -> moi dung duoc MediaStream/AudioContext)
                                              getUserMedia({audio:{mandatory:{chromeMediaSource:'tab', chromeMediaSourceId}}})
                                                -> MediaStreamAudioSourceNode
                                                     -> AudioContext.destination      (tra tieng lai cho nguoi dung:
                                                                                       Chrome mute tab khi bi capture)
                                                     -> AudioWorkletNode 'pcm-tap'    (fallback: createScriptProcessor)
                                                          -> down-mix mono
                                                          -> resample 16 kHz (noi suy tuyen tinh)
                                                          -> frame int16 LE 2048 mau (~4096 byte)
                                                          -> gate RMS < 0.004
                                                          -> ws.send()
                                              WS /ws/stream?sid=&partial=1&mode=&pin=
```

**Vi sao phai co offscreen document:** service worker cua MV3 khong co DOM, khong tao duoc
`MediaStream`/`AudioContext`, nen khong the tu tieu thu stream cua `chrome.tabCapture`.
Offscreen document la noi duy nhat lam duoc viec nay.

## File

| File | Vai tro |
|---|---|
| `manifest.json` | MV3. Permissions: `tabCapture`, `offscreen`, `storage`, `activeTab`. Khong khai bao icon. |
| `bg.js` | Service worker: dieu phoi START/STOP, tao/dong offscreen, goi `/session/create` + `/health`, giu state trong `chrome.storage.session`, phat su kien cho popup. |
| `offscreen.html` / `offscreen.js` | Bat audio tab, resample 16 kHz, dong goi frame, WebSocket + reconnect (5 lan, backoff). |
| `pcm-worklet.js` | AudioWorkletProcessor du phong (khi Blob URL bi CSP chan). |
| `popup.html` / `popup.js` | UI 340px: server URL, PIN, che do, nut bat/dung/mo phong/tao phong, log caption EN/VI. |

## Loi thuong gap

| Hien tuong | Nguyen nhan / cach xu ly |
|---|---|
| `tabCapture.getMediaStreamId: ...` | Tab `chrome://`, Chrome Web Store, hoac tab dang bi app khac chiem audio -> khong bat duoc. Chon tab khac. |
| `getUserMedia(tab): ...` | streamId chi dung duoc 1 lan va het han rat nhanh; bam lai "Bat dau dich tab nay". |
| `[loading] Model dang tai...` | Binh thuong: Whisper + NMT dang nap (1-2 phut lan dau). Cu de yen. |
| Khong nghe duoc tieng tab | AudioContext trong offscreen bi treo `suspended` (autoplay policy) -> xem log `AudioContext state=`. |
| `Mat ket noi WebSocket sau 5 lan thu` | Backend tat / sai cong. Bam "Kiem tra server". |
| Popup hien "chua chay" nhung audio van chay | Service worker bi Chrome tat (binh thuong). Bam lai icon: state duoc doc tu `chrome.storage.session` + `chrome.offscreen.hasDocument()`. |

## Kiem tra (khong can Chrome)

```bash
node -e "JSON.parse(require('fs').readFileSync('extension/manifest.json','utf8'));console.log('MANIFEST JSON OK')"
node --check extension/bg.js
node --check extension/offscreen.js
node --check extension/popup.js
node --check extension/pcm-worklet.js
node -e "const fs=require('fs');for(const f of ['extension/popup.html','extension/offscreen.html']){const h=fs.readFileSync(f,'utf8');const m=h.match(/<script>([\s\S]*?)<\/script>/);if(m)new (require('vm').Script)(m[1]);console.log(f,'OK')}"
```
