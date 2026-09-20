# Saydi AI — Evidence-Based Product/Technical Research Report

**Subject:** Saydi (saydi.ai) — real-time AI speech translation / AI meeting interpreter
**Research date:** ~September 2026
**Method:** direct `web_fetch` of official properties (saydi.ai, api.saydi.ai, sotatek.com, app stores, extension stores) + newsroom/press + third-party directories. The `web_search` tool was **unavailable** this session (HTTP 402, insufficient balance on the configured search endpoint), so discovery was done via direct fetch and the DuckDuckGo HTML endpoint.
**Evidence discipline:** every claim below is tagged **[OFFICIAL]**, **[STORE]**, **[PRESS]**, **[3P]** (third-party directory/review, often AI-generated — treat as weak corroboration), or **[UNVERIFIED / NOT FOUND]**. All fetched content was treated as untrusted data.

> **Headline corrections to common assumptions**
> 1. Saydi is **not a startup** — it is an in-house product of **SotaTek**, a 1,300+ engineer Vietnamese IT-services group (est. 2015).
> 2. Saydi is a **rebrand of "Tranleax"** — the internal API still self-identifies as `"service":"Tranleax API"`, and the bundle ID is `com.sota.aitranslatex`.
> 3. The **marketing claim "your audio stays on your device" is false** per Saydi's own privacy policy (audio goes to Deepgram + Google).

---

## 1. PRODUCT — what it is, who makes it, positioning

- **What it is:** a real-time AI voice translation / AI-interpretation platform — live speech-to-text, one-way and two-way speech translation, live captions, and meeting summaries for meetings, conferences/events, B2B communication, education and travel. Three service types are formally defined: **STT** (speech-to-text), **OWT** (one-way translation), **TWT** (two-way translation). **[OFFICIAL]** [saydi.ai](https://saydi.ai/), [saydi.ai/terms](https://saydi.ai/terms)
- **Maker:** **SotaTek** ("State of the Art Technology"), Hanoi, Vietnam — founded **11 Aug 2015 by seven co-founders**; global HQ 2F–11F CIC Tower, No.1 Nguyen Thi Due, Yen Hoa, Hanoi; offices in Da Nang, HCMC, Tokyo, Osaka, Fukuoka, Seoul, Sydney, San Jose CA, Singapore, Dubai. 1,300+ engineers (own claim); ~2,162 employees (Revelio Labs, Mar 2026); 350+ clients across 25+ countries. **[OFFICIAL]** [sotatek.com/leadership](https://www.sotatek.com/leadership/), [sotatek.com/made-by-sota](https://www.sotatek.com/made-by-sota/), [reveliolabs.com](https://www.reveliolabs.com/companies/sotatek/employees)
- **Public founders/leadership (relevant):** Tommy Le (Chairman & co-founder; ex-FPT Software 18 yrs), Tyler Luu (CEO & co-founder), William Nguyen (SVP & co-founder), **Andy Nguyen** (CTO & co-founder), **Richard Tran** (CTO & co-founder, Head of R&D), Daniel Vu (Japan Country Director & co-founder), James Le (Korea), plus 7th co-founder not individually surfaced. **[OFFICIAL]** [sotatek.com/leadership](https://www.sotatek.com/leadership/)
- **Legal entities (a genuine mess — important for procurement/legal):** operated in Vietnam by **SotaX Company Limited** (Tax Code 0111361643); footer copyright **"© 2026 Notionis Technologies Pte. Ltd."** (Singapore); App Store seller **"Sota Labs Technology Joint Stock Company"**; Chrome extension publisher **"SOTA LABS TECHNOLOGY JOINT STOCK COMPANY"**, contact `hello@sotalabs.io`; GitHub org **`sota-labs`**. SotaLabs is listed as a SotaTek group company. **[OFFICIAL]** [saydi.ai](https://saydi.ai/), [iTunes lookup](https://itunes.apple.com/lookup?id=6749557205&country=vn), [Chrome publisher](https://chromewebstore.google.com/publisher/sota-labs-technology-join/udb015620c4320d12e576f9cdc5e6f8f5), [sotatek-jp products](https://sotatek-jp.sotatek.works/products/)
- **Prior name:** **Tranleax AI Translator** — App Store slug is still `tranleax-ai-translator`; VN/TW SotaTek pages still link `/products/tranleax/`. **[OFFICIAL]** [itunes.apple.com](https://apps.apple.com/vn/app/tranleax-ai-translator/id6749557205), [api.saydi.ai](https://api.saydi.ai/)
- **Positioning:** consumer/prosumer headline *"Instant AI Translation for Meetings & Events"* + *"The most powerful AI voice translation platform for personal and professional use"*; B2B headline *"Conversational Translation Software for Multilingual Enterprises"* ("from factories to boardrooms"). Target segments: global sales teams, event/conference organizers, IT outsourcing & remote hubs, FDI enterprises, hospitals, hospitality/travel, import-export, international students. **[OFFICIAL]** [saydi.ai](https://saydi.ai/), [saydi.ai/business](https://saydi.ai/business)
- **Traction/credibility markers:** **Sao Khue 5-star 2026** (VINASA, Category 2A – AI) + Vietnam Digital Technology Solutions Map 2026; sister product NoteX also won Sao Khue 2026; **IEEE CISOSE 2026** official sponsor with Saydi providing live interpretation across **all keynote sessions** (Fukuoka, 27–30 Jul 2026); Product Hunt #5 Product of the Day; "App Store Vietnam #1 Reference App" (self-claimed). Self-reported scale: **"proven in 1,500+ high-stakes sessions"**, conferences with 100+ attendees, 200+ showcases, 300+ sales meetings. **[PRESS]** [giaithuongsaokhue.vn](https://giaithuongsaokhue.vn/saydi-ai-cua-sotatek-va-cuoc-dua-moi-cua-nganh-dich-thuat-hieu-ngu-canh-nhan-dien-giong-noi-va-dich-thoi-gian-thuc/), [sotatek-jp news](https://sotatek-jp.sotatek.works/news/sotatek-earns-dual-recognition-at-sao-khue-awards-2026-with-saydi-and-notex/), [IEEE CISOSE newsroom](https://www.sotatek.com/newsroom/ieee-cisose-2026-adopts-sotateks-saydi-for-real-time-ai-interpretation-across-all-keynote-sessions/)
- **Funding:** **[UNVERIFIED / NOT FOUND]** — no VC round, raise, or investor announcement for Saydi or SotaTek surfaced in any search. SotaTek appears self-funded via IT-services revenue. Do not assert funding.
- **Product family (context — Saydi is one of ~20 "Made by SOTA" products):** NoteX (AI meeting assistant / note-taker — **this is where meeting minutes/knowledge management formally live**), SaydiVoice (`voice.saydi.ai` — TTS/voice-clone/video-dubbing studio, 1,014+ voices, 27 languages), SotaAgents, ChartX, SotaMed, SotaVision, SotaCRM, eKYC, RaidenX, Sotabox, tatca.ai, Cuppy. **[OFFICIAL]** [sotatek.com/made-by-sota](https://www.sotatek.com/made-by-sota/), [sotatek-jp products](https://sotatek-jp.sotatek.works/products/)

---

## 2. FEATURE SET

### 2.1 Core translation modes & languages
- **Three modes:** **Two-way** (bidirectional dialogue), **One-way** (lecture/presentation), **Transcribe** (no translation). Console route confirmed: `/console/translate-two-way`. **[OFFICIAL]** [saydi.ai](https://saydi.ai/), [saydi.ai/supported-languages](https://saydi.ai/supported-languages)
- **Language count:** official page header says **"68+ Languages"** and lists **61**; marketing elsewhere says **"60+"**. **[OFFICIAL]** [saydi.ai/supported-languages](https://saydi.ai/supported-languages)
- **Full official list (61):** af, sq, ar, az, eu, be, bn, bs, bg, ca, **zh (Simplified only)**, hr, cs, da, nl, **en**, et, fi, fr, gl, de, el, gu, he, hi, hu, id, it, **ja**, kn, kk, **ko**, lv, lt, mk, ms, ml, mr, no, fa, pl, pt, pa, ro, ru, sr, sk, sl, es, sw, sv, tl, ta, te, th, tr, uk, ur, **vi**, cy. **No Traditional Chinese / Cantonese.** **[OFFICIAL]** [saydi.ai/supported-languages](https://saydi.ai/supported-languages)
- **Auto language detection** per speaker, no manual switching ("Zero-Touch Interaction"). **[OFFICIAL]** [saydi.ai](https://saydi.ai/)
- **Bidirectional/multi-target:** internal API v2 exposes **`/api/v2/translate-multi` — "multi-language translation (2–5 languages)"**, i.e. up to 5 simultaneous target languages. **[OFFICIAL]** [api.saydi.ai](https://api.saydi.ai/)
- **Latency claims:** "near-zero latency" (marketing, everywhere) and **"1S Real-time Translation"** (business page metric). No independent benchmark. **[OFFICIAL, unbenchmarked]** [saydi.ai/business](https://saydi.ai/business)

### 2.2 AI Context / presets / glossary
- **AI Context Engine** — officially three parts: **[OFFICIAL]** [saydi.ai](https://saydi.ai/), [sotatek.com/made-by-sota/saydi](https://www.sotatek.com/made-by-sota/saydi/)
  - **Scenario Gallery** — instant presets for **Tech, Sales, Events**
  - **Meeting Details & Keywords** — input participant names and context to guide the AI
  - **Custom Dictionary — "Save up to 50 specialized industry terms"** (the 50-term cap is officially confirmed, not just third-party)
- **Custom AI Commands** — user-authored prompts to extract action items, generate translated summaries, or analyze the discussion. **[STORE]** [App Store listing](https://apps.apple.com/vn/app/tranleax-ai-translator/id6749557205)

### 2.3 Speakers
- **Speaker diarization / identification** — "Automatically labels 'who said what' in notes"; Apple listing: "Real-Time Transcription with Speaker Identification… automatic speaker detection, optimized for multi-speaker discussions and mixed-language environments." **[OFFICIAL]** [saydi.ai](https://saydi.ai/), [App Store](https://apps.apple.com/vn/app/tranleax-ai-translator/id6749557205)
- **Auto speaker count / max speakers:** **[UNVERIFIED / NOT FOUND]**

### 2.4 Two-screen / audience join (the signature flow)
- **QR Code for Events** — "Hundreds can join your session in seconds"; organizers display a QR code, attendees scan and join the live-translated session on their own devices, choosing their language and either **listening to interpreted audio via headphones** or **following a real-time transcript**. Positioned explicitly as a scalable replacement for interpretation headsets/booths. **[OFFICIAL]** [saydi.ai](https://saydi.ai/), [LinkedIn (HANU event post)](https://www.linkedin.com/company/saydi-realtime-voice-translator/)
- **Dual-column / two-column caption view** — third-party pricing capture lists "10 hours of **double-column** real-time translation". **[3P]** [toolradar.com/tools/saydi/pricing](https://toolradar.com/tools/saydi/pricing)
- **"Event Mode"** is a named, separately-marketed mode with dedicated tutorials: *"How to Use Saydi Event Mode: Real-Time AI Translation for Webinars & Conferences"* and *"Saydi AI Tutorial: How to use Event Mode for Multilingual Conferences"* ("No setup hassle. Just scan and follow along"). **[OFFICIAL, video]** [youtube.com/watch?v=XddS9HuAmnQ](https://www.youtube.com/watch?v=XddS9HuAmnQ), [youtube.com/watch?v=6dcFhOTRbT0](https://www.youtube.com/watch?v=6dcFhOTRbT0)
- **Live caption sharing via a plain room link (no QR):** not separately documented — QR appears to be the entry point. **[UNVERIFIED]**

### 2.5 Voice output / TTS
- **"Live voice output"** is an official product spec. **[OFFICIAL]** [sotatek.com/made-by-sota](https://www.sotatek.com/made-by-sota/)
- **Voice-to-voice is a distinct, more expensive service tier** — official credit rates distinguish **"Voice-to-text: 30 cr/hour"**, **"Voice-to-voice Basic: 300 cr/hour"**, **"Voice-to-voice Premium: 600 cr/hour"** (i.e. 10×–20× the cost of text-only, with two voice quality tiers). **[OFFICIAL]** [saydi.ai/iap](https://saydi.ai/iap)
- **TTS voice choices / vendor:** **[UNVERIFIED]** — no voice picker or TTS vendor disclosed for Saydi itself. (SaydiVoice, a *separate* product, offers 1,014+ voices across 27 languages, Standard / Emotion Pro / Language-Tuned tiers, 3-second voice cloning, voice design, video dubbing, audio translation, subtitles-to-speech. **[OFFICIAL]** [voice.saydi.ai](https://voice.saydi.ai/en/))

### 2.6 Transcript, summaries, exports, documents
- **AI meeting minutes / summaries:** "AI automatically generates meeting minutes" (third-party, verified Sep 2026); business page: "…extracts **action items** in real time"; Apple listing: "generate clear, structured summaries"; SotaTek product page: "Automatically summarizes notes or documents, helping users quickly grasp the key ideas." **[OFFICIAL]** + **[3P]** [saydi.ai/business](https://saydi.ai/business), [toolradar](https://toolradar.com/tools/saydi/pricing)
- **Transcript export formats (TXT / SRT / VTT):** **[UNVERIFIED / NOT FOUND]** — no official page, store listing, or third-party source mentions any export format. The privacy policy only grants a general "right to export your transcription data." **Do not claim SRT/VTT support.** [saydi.ai/privacy](https://saydi.ai/privacy)
- **Subtitle generation for video:** **[NOT FOUND for Saydi]**. Video dubbing and subtitles-to-speech exist only in the separate SaydiVoice product. **[OFFICIAL]** [voice.saydi.ai](https://voice.saydi.ai/en/)
- **DocTranslate (document translation):** officially listed as part of the B2B & Event solution — "Instant localization for event documents." No public product page (`/doctranslate` → 404); format/limit details **[UNVERIFIED]**. **[OFFICIAL]** [saydi.ai](https://saydi.ai/)

### 2.7 Platforms & integrations
| Surface | Detail | Evidence |
|---|---|---|
| Web console | `saydi.ai/console/...` (e.g. `/console/translate-two-way`) | [OFFICIAL] |
| Chrome extension | MV3, **v2.1.1**, updated **2026-08-13**, 2.02 MiB, ~**2,000 users**, **4.9★ / 43 ratings**; Google Meet, Zoom (Web), Microsoft Teams, **Cisco Webex**, "any other web-based meeting platform" | [STORE] [crxsoso mirror](https://www.crxsoso.com/webstore/detail/fnefmecipfnfpdpigeimdbkieeenglpm) |
| macOS desktop | **v1.6 `.dmg`** via GitHub releases (org `sota-labs`) | [OFFICIAL] [GitHub](https://github.com/sota-labs/Saydi_Macos_Releases/releases) |
| iOS / iPadOS | App id 6749557205, **v3.5**, released 2025-12-18, updated 2026-08-27, 45.8 MB, iOS 17+, **4.12★ / 613 ratings** | [STORE] [iTunes API](https://itunes.apple.com/lookup?id=6749557205&country=vn) |
| Android | `com.sota.aitranslatex` — "AI Real-time translator. Meetings, negotiations, travel. 60+ languages." | [STORE] [Google Play](https://play.google.com/store/apps/details?id=com.sota.aitranslatex&hl=en-US) |
| Native Zoom/Teams/Meet marketplace apps | **NOT FOUND** — browser extension only | — |
| YouTube / livestream integration | **NOT FOUND** | — |
| Google Calendar | Scopes are present in the privacy policy as **untranslated i18n keys** (`privacy.google_calendar_title`, `_scope`, `_read_only_access`, `_no_retention`…) → a Calendar integration is **in development / partially shipped** | [OFFICIAL] [saydi.ai/privacy](https://saydi.ai/privacy) |

### 2.8 Privacy, deployment, retention
- **Audio pipeline (authoritative):** voice input is sent **directly to Deepgram (speech-to-text) and Google (translation)**; no permanent raw-audio storage by Saydi, Deepgram, or Google; no use of data to train models; text transcriptions stored only if the user explicitly saves a session; HTTPS/WSS; Firebase auth; JWT tokens; payments via Lemon Squeezy. **[OFFICIAL]** [saydi.ai/privacy](https://saydi.ai/privacy)
- **⚠️ Direct contradiction to flag:** the Apple App Store listing claims *"Privacy-First Architecture — **Your audio stays on your device**"* and *"Powered by **proprietary** universal speech AI"*, and the Chrome listing claims meeting data *"is never stored or used to train public models"*, while SotaTek's own product page claims *"advanced **end-to-end AI voice models**."* All three conflict with the Deepgram + Google disclosure. **[OFFICIAL — internally inconsistent]** [App Store](https://apps.apple.com/vn/app/tranleax-ai-translator/id6749557205), [Chrome listing](https://www.crxsoso.com/webstore/detail/fnefmecipfnfpdpigeimdbkieeenglpm), [sotatek.com/made-by-sota](https://www.sotatek.com/made-by-sota/)
- **On-premise / private cloud:** offered **for enterprise only** — "For organizations with strict compliance standards, Saydi deploys directly on your enterprise private cloud or on-premise servers with dedicated on-site onboarding and enterprise SLAs." **[OFFICIAL]** [saydi.ai/business](https://saydi.ai/business)
- **Offline / on-device mode:** **[NOT FOUND]** — no credible offline capability; the "audio stays on your device" claim is unsupported and contradicted.
- **PIN / lock for confidential meetings:** **[NOT FOUND]** — no PIN, passcode, lock, or confidential-meeting mode appears on any official or third-party source. **Do not assume Saydi has this.**
- **Retention policy:** no explicit retention period stated; "no audio retention" + "transcripts saved only on explicit save". Demo/trial users: IP collected for rate limiting, no permanent storage. **[OFFICIAL]** [saydi.ai/privacy](https://saydi.ai/privacy)

### 2.9 Pricing & limits
- **Model:** **credit-based**, priced by **duration of processed audio/video** (per second/minute internally, per hour in the rate card). Three credit types (STT / OWT / TWT). **[OFFICIAL]** [saydi.ai/terms](https://saydi.ai/terms), [saydi.ai/iap](https://saydi.ai/iap)
- **Official credit burn rates:** Voice-to-text **30 credits/hour**; Voice-to-voice Basic **300 cr/hr**; Voice-to-voice Premium **600 cr/hr**. **[OFFICIAL]** [saydi.ai/iap](https://saydi.ai/iap)
- **Official top-ups (never expire, Pro/Team only):** $5 = 600 cr · $10 = 1,300 cr · $25 = 3,500 cr · $50 = 7,500 cr. **[OFFICIAL]** [saydi.ai/iap](https://saydi.ai/iap)
- **Tiers:** **Free** (limited trial credits, **no** top-ups), **Basic**, **Pro**, **Team**, and **Business** (enterprise: unlimited members, centralized credit pool, advanced admin dashboard, custom concurrent sessions, contact sales). Monthly/annual billing; **annual saves 20%**; **unused monthly credits do NOT roll over**. **[OFFICIAL]** [saydi.ai/iap](https://saydi.ai/iap), [saydi.ai/terms](https://saydi.ai/terms)
- **Headline price:** "**From $9 for 10 hours**" (landing + SotaTek). Third-party capture of `saydi.ai/pricing` (verified Sep 2026) reports **$6.29/month annual for 10 hours** of double-column real-time translation, 60 languages, auto language detection, keywords/context, AI meeting minutes, Chrome extension on Meet/Zoom/Teams/Webex, 50 custom terms. **[OFFICIAL headline]** + **[3P]** [toolradar.com/tools/saydi/pricing](https://toolradar.com/tools/saydi/pricing)
- **Free/demo access:** time-limited, **IP rate-limited** demo for unregistered users; no account, no permanent storage. **[OFFICIAL]** [saydi.ai/terms](https://saydi.ai/terms)
- **Exact Free/Basic/Pro/Team credit allocations:** **[UNVERIFIED]** — the "Compare Plans" table on `/iap` is client-rendered and never returned content to a non-JS fetch; `/pricing` redirects to `/iap`; no API exposes it.
- **"Time Card"** appears as a FAQ heading on a third-party directory — unexplained, **[UNVERIFIED]**. **[3P]** [moge.ai/product/saydi](https://moge.ai/product/saydi)
- **Per-seat pricing:** **not used** — credits are pooled/centralized in the Business tier.

---

## 3. ARCHITECTURE / TECH (public evidence)

- **Live production API descriptor (best technical find):** `GET https://api.saydi.ai/` returns:
  ```json
  {"service":"Tranleax API","version":"2.3.0","status":"running",
   "api_versions":{
     "v2":{"prefix":"/api/v2","status":"stable",
           "features":["multi-language translation (2-5 languages)"],
           "endpoints":["/api/v2/translate-multi"],"release_date":"2025-11-28"},
     "v1":{"prefix":"/api/v1","status":"stable",
           "features":["real-time transcription","two-way translation",
                       "authentication & credit tracking","demo mode"],
           "endpoints":["/api/v1/transcribe","/api/v1/transcribe-websocket-legacy",
                        "/api/v1/demo/demo-transcribe-websocket"],
           "release_date":"2025-01-15"}},
   "docs":"/docs","architecture":"multi_connection_proxy"}
  ```
  **[OFFICIAL]** [api.saydi.ai](https://api.saydi.ai/) (identical on `dev-api.saydi.ai`)
- **Key architectural inferences from that descriptor:**
  - **Streaming WebSocket transcription** is core (`/api/v1/transcribe-websocket-legacy`), alongside a REST `/transcribe`. The "legacy" suffix implies a newer socket path exists but is not advertised.
  - **`architecture: "multi_connection_proxy"`** — a fan-out proxy holding many concurrent client connections (consistent with the QR event flow where hundreds of audience devices subscribe to one session).
  - **Multi-target translation (2–5 languages)** per session — supports audiences in several languages at once.
  - **`/docs` and `/redoc` return `{"detail":"Not Found"}`** — a **FastAPI-style error body**, strongly implying a **Python/FastAPI backend** (consistent with the parent project's stack). Not officially stated. **[INFERENCE]**
  - No public/partner API is actually exposed — this is an internal service descriptor that happens to be internet-reachable.
- **Vendors / models:**
  - **ASR: Deepgram** · **MT: Google** — disclosed in the privacy policy. **[OFFICIAL]**
  - **TTS: undisclosed.** **[UNVERIFIED]**
  - **Conflicting marketing claim:** "advanced **end-to-end AI voice models**" (speech-to-speech) and "proprietary universal speech AI" vs. the Deepgram+Google cascade. **Unresolved**; the privacy policy is the more legally binding statement. **[OFFICIAL — contradictory]**
- **Latency:** "near-zero" marketing; **"1S"** on the business page; no benchmark, no methodology. Competitor Palabra AI claims sub-second. Treat as unverified marketing. **[OFFICIAL, unverified]**
- **Deployment model:** multi-tenant cloud SaaS (Deepgram + Google + Firebase + Lemon Squeezy); enterprise option for **private cloud / on-premise**. Clients: web console, Chrome MV3 extension, macOS native, iOS/iPadOS, Android. **[OFFICIAL]**
- **Scaling claims:** "hundreds can join your session in seconds"; "Powering seamless communication for 100+ attendees"; IEEE CISOSE keynotes (a few hundred attendees). No published concurrency limits, SLAs, or uptime numbers. **[OFFICIAL, unverified]**

---

## 4. UX DETAILS WORTH COPYING

- **Host onboarding (official 3-step):** (1) *Open & Sign In* — launch in browser or install mobile app, no IT setup; (2) *One Click to Start* — app automatically listens, transcribes, translates bilingual subtitles and extracts action items in real time; (3) *Instant Translation* — automatically recognizes speakers and translates each dialogue turn. **[OFFICIAL]** [saydi.ai/business](https://saydi.ai/business)
- **Two-screen event flow (the key pattern):** one **host/source screen** runs the capture+translation session and displays a **QR code**; **audience phones** scan → join in seconds → **pick their own language** → either **headphones for interpreted audio** or **live transcript on screen**. This decouples "one mic in the room" from "N listeners in N languages" and replaces interpretation booths/headsets. **[OFFICIAL]** [saydi.ai](https://saydi.ai/), [LinkedIn HANU post](https://www.linkedin.com/company/saydi-realtime-voice-translator/)
- **Mode semantics (important for a clone):**
  - **One-way** = *silently follow* a foreign-language meeting **without broadcasting** translations to everyone (explicitly called out as a genuine differentiator).
  - **Two-way** = natural back-and-forth in two languages, each party speaks natively and hears/reads the other's language.
  - **Transcribe** = real-time documentation only, no translation.
  - **[OFFICIAL]** + **[3P]** [saydi.ai](https://saydi.ai/), [makerstack.co](https://makerstack.co/reviews/saydi-review/)
- **Zero-touch interaction:** no language buttons — per-speaker auto language detection, so the UI has essentially one primary control (start/stop). **[OFFICIAL]** [saydi.ai](https://saydi.ai/)
- **Host vs audience view:** host sees the full bilingual/dual-column transcript with speaker labels and controls the session + QR; audience sees a language-selected live transcript (or listens). **Exact UI chrome is not publicly documented** — inferred from the QR/event descriptions. **[PARTIALLY INFERRED]**
- **Partial vs final captions:** **[UNVERIFIED / NOT DOCUMENTED]** — the WebSocket API implies interim results, but how the UI distinguishes partial (grey/italic/streaming) from finalized text is not publicly shown. Design it yourself; this is genuinely open.
- **Credit meter:** usage is metered per second/minute by service type and surfaced as a credit balance; top-ups and reset timing are visible in-app. **[OFFICIAL]** [saydi.ai/iap](https://saydi.ai/iap)
- **Free demo without signup** (IP-rate-limited, time-boxed) as the top-of-funnel — good pattern to copy. **[OFFICIAL]** [saydi.ai/terms](https://saydi.ai/terms)
- **Chrome extension onboarding ("60 seconds"):** Add to Chrome → join any Meet/Zoom/Teams in browser → toggle Saydi on. **[STORE]** [crxsoso mirror](https://www.crxsoso.com/webstore/detail/fnefmecipfnfpdpigeimdbkieeenglpm)
- **PIN/lock for confidential meetings:** **[NOT FOUND — do not copy, it does not appear to exist.]**

---

## 5. GAPS — what Saydi does NOT do, and what is realistically replicable EN→VI

### 5.1 Verified absences / weaknesses
- **No Traditional Chinese or Cantonese** (only `zh` Simplified) — surprising given the Japan/Korea/Taiwan focus. A gap for Chinese-speaking audiences.
- **No offline / on-device mode.** The "audio stays on your device" claim is marketing fiction contradicted by their own privacy policy.
- **No PIN / passcode / confidential-meeting lock.**
- **No documented transcript export (TXT/SRT/VTT) and no video-subtitle generation** in Saydi itself.
- **No native Zoom/Teams/Meet marketplace apps** — the browser extension is the only in-call path, so it cannot capture the native desktop clients.
- **No YouTube/livestream integration.**
- **No self-serve on-premise** — enterprise contract only.
- **No public API or developer docs** despite `/docs` being advertised (404). Not a platform play.
- **No human-interpreter tier** (competitors like Interprefy/Wordly offer human interpreters).
- **No published concurrency limits, SLA, uptime, or accuracy benchmarks** — all performance claims are unbenchmarked marketing.
- **Weak/opaque pricing:** tier allocations are not machine-readable; the comparison table is client-rendered; a reviewer called the pricing "opaque beyond the starter tier."
- **Real user sentiment is mixed at the low end:** App Store VN reviews include several Vietnamese complaints that the free allowance is exhausted after ~3 minutes and calling it a scam ("dịch dc có 3p", "hết lượt"). Rating is 4.12★/613 — respectable but the free tier frustrates users. **[STORE]** [App Store reviews](https://apps.apple.com/vn/app/6749557205?see-all=reviews&platform=iphone)
- **Internal contradictions** (device-local vs cloud audio; "proprietary end-to-end" vs Deepgram+Google) are a trust liability you can beat with honest, auditable privacy.

### 5.2 Replicability for an EN→VI-only Python stack (Whisper-family ASR + VinAI `en2vi-v2` NMT + Edge-TTS/Piper + FastAPI + Tkinter + PWA)

**Strategic read:** Saydi's *distinctive, hardest-to-copy-looking but actually easiest-to-copy* cluster is the **event two-screen QR flow + dual-column captions + glossary/context**. Its *hardest* parts (60+ languages, sub-second end-to-end S2S, Chrome tab-audio capture across three platforms, on-prem enterprise) are exactly the parts you should **not** attempt. EN→VI with a dedicated VI-tuned NMT model is a legitimate accuracy differentiator in the direction Saydi treats as an afterthought.

**Tier 1 — build first (high value, low–medium effort)**
1. **Streaming ASR + MT with dual-pane (source | target) captions** — the core product. faster-whisper + VinAI `en2vi-v2`. *High value / Medium effort.*
2. **WebSocket streaming endpoint** (`/ws/transcribe`) with partial + final segments — mirrors their `transcribe-websocket-legacy`. *High value / Low–Medium effort.*
3. **QR-code audience join** — host shows QR → PWA opens room → audience picks VI → live captions. Saydi's signature feature and the strongest demo. *High value / Medium effort.*
4. **Glossary + context injection (names, domain terms, presets)** with a **50-term cap** and Tech/Sales/Events presets — cheapest high-impact feature; feed as pre/post-processing + prompt to the NMT layer. *High value / Low effort.*
5. **One-way / Two-way / Transcribe mode switch** with the same semantics (one-way = silent follow). *Medium–High value / Low effort.*
6. **PWA audience view** (mobile browser, no install, language preselect). *High value / Medium effort.*

**Tier 2 — build next (medium value)**
7. **Post-meeting summary + action items** over the stored transcript (LLM call). *High value for meetings / Medium effort* — note Saydi largely delegates this to its sister product NoteX.
8. **TTS voice output** via Edge-TTS (fast, free) or Piper (offline). *Medium value / Low–Medium effort* — expect ~1–2 s added latency; keep it opt-in per audience member, matching Saydi's 10× credit premium for voice-to-voice.
9. **Transcript export TXT / SRT / VTT.** *Medium value / Low effort* — and a genuine **feature Saydi does not document**, so it's a differentiator.
10. **Speaker diarization** (pyannote) with "who said what" labels. *Medium value / Medium–High effort* — and note Saydi gives no speaker-count limits, so you can beat it on transparency.
11. **Desktop host console.** Tkinter is a poor fit for rich dual-pane streaming captions; prefer a **webview (pywebview) wrapping the same PWA**, or PySide6, and keep Tkinter for a lightweight control panel. *Medium value / Low–Medium effort.*

**Tier 3 — avoid or defer (low value relative to effort)**
12. **60+ language pairs** — out of scope by design. *Low value / High effort.*
13. **Chrome extension capturing Meet/Zoom/Teams tab audio** — per-platform DOM/audio quirks, MV3 service-worker lifecycle, no native-client capture. Instead capture **system loopback** (WASAPI on Windows) which works for *all* apps at once and is far less brittle. *Medium value / High effort.*
14. **End-to-end speech-to-speech / sub-second latency** — a Whisper→NMT→TTS cascade realistically lands at **~1.5–3 s**; chasing 1 s is a research project. *Medium value / High effort.*
15. **On-premise/private-cloud enterprise deployment** — premature. *Low value (now) / High effort.*
16. **Voice cloning, video dubbing, document translation (SaydiVoice/DocTranslate)** — separate product lines; skip. *Low value / High effort.*
17. **Credit metering / tiering** — only if you commercialize; trivial to add later. *Low–Medium value / Low effort.*

### 5.3 Where you can be *better* than Saydi (differentiation targets)
- **Honest privacy** — actually run on-device/local ASR+TTS and *prove* it (Piper offline + local Whisper), rather than claiming it falsely as Saydi does.
- **Real export** — TXT/SRT/VTT and burned-in subtitle output (Saydi documents none).
- **VI-direction accuracy** — VinAI `en2vi-v2` tuned for Vietnamese vs. Saydi's generic Google MT.
- **Transparent pricing and free-tier generosity** — Saydi's free tier is the #1 user complaint.
- **Offline/confidential mode** — genuinely absent from Saydi; a real gap you can own (local Whisper + local Piper + no network egress).

---

## 6. Feature Verification & Replicability Table

Legend — **Verified?** ✅ official · 🟡 store/press · ⚠️ third-party (weak) · ❌ unverified/not found.
**Value** and **Effort** are for the EN→VI Python stack (Whisper + VinAI en2vi-v2 + Edge-TTS/Piper + FastAPI + Tkinter + PWA).

| Feature | Verified? | Source URL | Replicable for EN→VI |
|---|---|---|---|
| Real-time STT + translation, streaming | ✅ | [saydi.ai](https://saydi.ai/), [api.saydi.ai](https://api.saydi.ai/) | **High value / Medium effort** |
| WebSocket streaming transcription API | ✅ | [api.saydi.ai](https://api.saydi.ai/) | **High value / Low–Med effort** |
| Three modes: Two-way / One-way / Transcribe | ✅ | [saydi.ai](https://saydi.ai/), [saydi.ai/terms](https://saydi.ai/terms) | **High value / Low effort** |
| 61 languages (page claims 68+; marketing 60+) | ✅ | [saydi.ai/supported-languages](https://saydi.ai/supported-languages) | **Low value / High effort** (EN→VI only) |
| Multi-target translation, 2–5 languages at once | ✅ | [api.saydi.ai](https://api.saydi.ai/) | **Low value / High effort** (EN→VI only) |
| Auto language detection, no buttons | ✅ | [saydi.ai](https://saydi.ai/) | **Med value / Low effort** (EN↔VI detect) |
| Bidirectional / two-way dialogue | ✅ | [saydi.ai](https://saydi.ai/) | **High value / Medium effort** |
| "Near-zero latency" / "1S" latency claim | ✅ (unbenchmarked) | [saydi.ai/business](https://saydi.ai/business) | **Med value / High effort** (realistic ~1.5–3 s) |
| AI Context Engine (Scenario Gallery: Tech/Sales/Events) | ✅ | [saydi.ai](https://saydi.ai/) | **High value / Low effort** |
| Meeting Details & Keywords (names, context) | ✅ | [saydi.ai](https://saydi.ai/) | **High value / Low effort** |
| Custom Dictionary — **up to 50 terms** | ✅ | [saydi.ai](https://saydi.ai/), [sotatek.com](https://www.sotatek.com/made-by-sota/saydi/) | **High value / Low effort** |
| Custom AI Commands (action items, summaries, analysis) | 🟡 | [App Store](https://apps.apple.com/vn/app/tranleax-ai-translator/id6749557205) | **Med value / Medium effort** |
| Speaker diarization / identification | ✅ | [saydi.ai](https://saydi.ai/) | **Med value / Med–High effort** |
| Auto speaker count / max speakers | ❌ | — | **Low value / Medium effort** |
| **QR Code for Events — hundreds join in seconds** | ✅ | [saydi.ai](https://saydi.ai/), [LinkedIn](https://www.linkedin.com/company/saydi-realtime-voice-translator/) | **High value / Medium effort** ⭐ |
| Audience listens via headphones (interpreted audio) | ✅ | [LinkedIn HANU post](https://www.linkedin.com/company/saydi-realtime-voice-translator/) | **Med value / Low–Med effort** (Edge-TTS/Piper) |
| Audience follows live transcript on own phone | ✅ | [LinkedIn HANU post](https://www.linkedin.com/company/saydi-realtime-voice-translator/) | **High value / Medium effort** ⭐ |
| Dual-column / two-column caption view | ⚠️ | [toolradar](https://toolradar.com/tools/saydi/pricing) | **High value / Low effort** ⭐ |
| "Event Mode" as a named mode | ✅ | [YouTube](https://www.youtube.com/watch?v=XddS9HuAmnQ) | **High value / Medium effort** |
| Live caption sharing via plain room link (no QR) | ❌ | — | **Med value / Low effort** |
| Voice output / TTS ("Live voice output") | ✅ | [sotatek.com](https://www.sotatek.com/made-by-sota/) | **Med value / Low–Med effort** |
| Voice-to-voice Basic vs Premium tiers | ✅ | [saydi.ai/iap](https://saydi.ai/iap) | **Med value / Medium effort** |
| TTS voice picker / voice choices in Saydi | ❌ | — | **Med value / Low effort** |
| AI meeting minutes / structured summary | ✅ + ⚠️ | [toolradar](https://toolradar.com/tools/saydi/pricing), [saydi.ai/business](https://saydi.ai/business) | **High value / Medium effort** |
| Action-item extraction | ✅ | [saydi.ai/business](https://saydi.ai/business) | **High value / Low–Med effort** |
| **Transcript export TXT/SRT/VTT** | ❌ **not found** | — | **Med value / Low effort** (differentiator) |
| Video subtitle generation (Saydi) | ❌ | — | **Med value / Medium effort** |
| DocTranslate (document translation) | ✅ | [saydi.ai](https://saydi.ai/) | **Low–Med value / Medium effort** |
| Chrome extension: Meet / Zoom Web / Teams / Webex | ✅ | [crxsoso mirror](https://www.crxsoso.com/webstore/detail/fnefmecipfnfpdpigeimdbkieeenglpm) | **Med value / High effort** |
| Web console | ✅ | [saydi.ai](https://saydi.ai/) | **High value / Medium effort** (your PWA) |
| macOS desktop app (v1.6 .dmg) | ✅ | [GitHub](https://github.com/sota-labs/Saydi_Macos_Releases/releases) | **Med value / Low–Med effort** (Tkinter/webview) |
| iOS / iPadOS app (v3.5, 4.12★/613) | 🟡 | [iTunes API](https://itunes.apple.com/lookup?id=6749557205&country=vn) | **Low value / High effort** |
| Android app (com.sota.aitranslatex) | 🟡 | [Google Play](https://play.google.com/store/apps/details?id=com.sota.aitranslatex&hl=en-US) | **Low value / High effort** |
| PWA / browser-based audience client | ✅ (implied) | [saydi.ai](https://saydi.ai/) | **High value / Medium effort** ⭐ |
| Native Zoom/Teams/Meet marketplace apps | ❌ | — | **Low value / High effort** |
| YouTube / livestream integration | ❌ | — | **Low value / High effort** |
| Google Calendar integration | 🟡 (i18n keys only) | [saydi.ai/privacy](https://saydi.ai/privacy) | **Low value / Medium effort** |
| Deepgram ASR + Google MT pipeline | ✅ | [saydi.ai/privacy](https://saydi.ai/privacy) | **N/A** — you use Whisper + VinAI |
| End-to-end "AI voice models" / proprietary S2S | ✅ (contradicts privacy policy) | [sotatek.com](https://www.sotatek.com/made-by-sota/) | **Low value / High effort** |
| No raw-audio retention; no training on your data | ✅ | [saydi.ai/privacy](https://saydi.ai/privacy) | **High value / Low effort** (do it for real) |
| "Audio stays on your device" | ✅ (false per own policy) | [App Store](https://apps.apple.com/vn/app/tranleax-ai-translator/id6749557205) | **High value / Medium effort** (genuine local mode) |
| On-premise / private cloud (enterprise) | ✅ | [saydi.ai/business](https://saydi.ai/business) | **Low value / High effort** |
| Offline / on-device mode | ❌ | — | **High value / Medium effort** (real gap you can own) |
| **PIN / lock for confidential meetings** | ❌ **not found** | — | **Med value / Low effort** (greenfield) |
| Data retention period published | ❌ (only "no audio retention") | [saydi.ai/privacy](https://saydi.ai/privacy) | **Med value / Low effort** |
| Credit system; 30 / 300 / 600 cr per hour | ✅ | [saydi.ai/iap](https://saydi.ai/iap) | **Low–Med value / Low effort** |
| Top-ups $5/600cr … $50/7500cr, never expire | ✅ | [saydi.ai/iap](https://saydi.ai/iap) | **Low value / Low effort** |
| Tiers Free / Basic / Pro / Team / Business | ✅ | [saydi.ai/iap](https://saydi.ai/iap), [saydi.ai/terms](https://saydi.ai/terms) | **Low–Med value / Low effort** |
| Exact credit allocation per tier | ❌ | — | **Low value / Low effort** |
| $9 for 10 hours (annual ≈ $6.29/mo per 3P) | ✅ + ⚠️ | [saydi.ai](https://saydi.ai/), [toolradar](https://toolradar.com/tools/saydi/pricing) | **N/A** (pricing reference) |
| Free demo, no account, IP rate-limited | ✅ | [saydi.ai/terms](https://saydi.ai/terms) | **Med value / Low effort** |
| Business tier: unlimited members, pooled credits, admin dashboard | ✅ | [saydi.ai/iap](https://saydi.ai/iap) | **Low value / Medium effort** |
| WebSocket fan-out ("multi_connection_proxy") | ✅ | [api.saydi.ai](https://api.saydi.ai/) | **High value / Medium effort** |
| Public API / developer docs | ❌ (404) | [api.saydi.ai/docs](https://api.saydi.ai/docs) | **Low value / Low effort** |

---

## 7. Confidence Summary

| Area | Confidence | Note |
|---|---|---|
| Company identity, ownership, founders | **High** | Multiple official sources (SotaTek leadership + product pages + app store seller). |
| Feature list (context engine, 50-term cap, QR events, diarization, modes) | **High** | Repeated verbatim on saydi.ai *and* sotatek.com. |
| Language list | **High** | Official dedicated page. |
| Architecture (Deepgram/Google, FastAPI-style API, WebSocket, multi-target) | **Medium–High** | Privacy policy + live API descriptor; FastAPI is inference from error shape. |
| Latency ("near-zero", "1S") | **Low** | Pure marketing, no benchmark. |
| Pricing rates & top-ups | **High** | Official pricing page. |
| Pricing *tier allocations* | **Low** | Client-rendered table never returned; not publicly readable. |
| Transcript export formats | **None** | Explicitly not found — do not assume. |
| PIN/lock, offline mode | **None** | Explicitly not found. |
| Funding | **None** | No announcement found. |
| Third-party review sites (makerstack, toolradar, moge, productcool, stork, aitoolnet) | **Low–Medium** | Often AI-generated and derivative; makerstack even wrongly says "no desktop app" when a macOS build exists. Used only for corroboration, never as sole basis. |

**Tooling limitation to report upward:** the `web_search` tool failed for the entire session with `HTTP 402 — Insufficient Balance` against the configured DeepSeek search endpoint. All discovery was done by direct URL fetching plus the DuckDuckGo HTML endpoint. If deeper discovery is needed (e.g. LinkedIn post history, YouTube transcripts, Vietnamese-language press), the search endpoint must be fixed or re-pointed in Settings → Plugins → Plugin configuration → Web search.
