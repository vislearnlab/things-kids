// THINGS Kids — Picture Detective. Semantic-outlier oddity task using
// stimuli from vocab-gradient (300x300 THINGS-derived photos) and adult
// difficulty scores from the SPoSE model (Hebart et al. 2023).
//
// jsPsych v8 experiment, TypeScript module bundled by Vite. Same UX
// scaffold as mochi-kids: consent -> welcome -> how-to-play -> training
// -> warmup -> shuffled test block (familiar + catch).

import { initJsPsych } from 'jspsych';
import jsPsychHtmlButtonResponse from '@jspsych/plugin-html-button-response';
import jsPsychHtmlKeyboardResponse from '@jspsych/plugin-html-keyboard-response';
import jsPsychPreload from '@jspsych/plugin-preload';
import { consentHTML, consentPlainText, CONSENT_AGREEMENT_LINE,
         CONSENT_STUDY_TITLE, CONSENT_STUDY_NUMBER } from './consent_adult';
import 'jspsych/css/jspsych.css';
import './assets/styles.css';

// ============ helpers ============
function getURLParam(name: string, fallback: string | null): string | null {
  const u = new URL(window.location.href);
  return u.searchParams.get(name) || fallback;
}
function shortId(n = 10): string {
  const s = 'abcdefghijkmnpqrstuvwxyz23456789';
  let r = '';
  for (let i = 0; i < n; i++) r += s.charAt(Math.floor(Math.random() * s.length));
  return r;
}

// ============ boot overlay (visible loading + error reporter) ============
function bootSay(msg: string)  { const e = document.getElementById('boot-msg');   if (e) e.textContent = msg; }
function bootFail(msg: string) {
  const e = document.getElementById('boot-error');
  if (!e) return;
  e.style.display = 'block';
  e.textContent = (e.textContent ? e.textContent + '\n\n' : '') + msg;
}
function bootDone()            { const ov = document.getElementById('boot-overlay'); if (ov) ov.remove(); }
window.addEventListener('error', (e) => bootFail(`JS error: ${e.message || e.error || e}\n${e.filename || ''}:${e.lineno}`));
window.addEventListener('unhandledrejection', (e: any) => bootFail(`Promise rejected: ${e.reason && (e.reason.stack || e.reason.message) || e.reason}`));
if (location.protocol === 'file:') {
  bootFail('Looks like you opened this file directly (file://). The browser blocks fetch() over file://, so the trial manifest can\'t load.\n\nFix: from the project root, run\n   npm run dev\nthen open the URL it prints (usually http://localhost:3000).');
}

// ============ audio: 3 spoken prompts + Web Audio chime ============
const AUDIO_BASE = 'audio';
const audioCache: Record<string, HTMLAudioElement> = {};
function loadAudio(name: string): HTMLAudioElement {
  if (audioCache[name]) return audioCache[name];
  const a = new Audio(`${AUDIO_BASE}/${name}.m4a`);
  a.preload = 'auto';
  audioCache[name] = a;
  return a;
}
let lastPrompt: HTMLAudioElement | null = null;
function playPrompt(name: string): HTMLAudioElement {
  // Reuse the same cached <audio> element — never clone. iOS Safari only
  // grants playback permission to elements that received a user gesture
  // (cached + primed by unlockAudio); a freshly cloned node is treated as
  // unprimed and play() gets silently blocked. Just rewind and play.
  const a = loadAudio(name);
  if (lastPrompt && lastPrompt !== a && !lastPrompt.paused) {
    try { lastPrompt.pause(); lastPrompt.currentTime = 0; } catch (_) {}
  }
  try { a.currentTime = 0; } catch (_) {}
  a.play().catch(() => {});
  lastPrompt = a;
  return a;
}

let audioCtx: AudioContext | null = null;
function ac(): AudioContext | null {
  if (!audioCtx) {
    const C = (window as any).AudioContext || (window as any).webkitAudioContext;
    if (!C) return null;
    audioCtx = new C();
  }
  if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
  return audioCtx;
}
function playChime(): void {
  const ctx = ac(); if (!ctx) return;
  const now = ctx.currentTime;
  const notes = [523.25, 659.25, 783.99, 1046.50]; // C–E–G–C arpeggio
  notes.forEach((freq, i) => {
    const t0 = now + i * 0.07;
    const osc = ctx.createOscillator();
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(freq, t0);
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0, t0);
    gain.gain.linearRampToValueAtTime(0.18, t0 + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.55);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t0); osc.stop(t0 + 0.6);
  });
}

// iOS Safari needs a real user gesture before any audio can play.
let audioUnlocked = false;
function unlockAudio(): void {
  if (audioUnlocked) return;
  audioUnlocked = true;
  ac();
  ['intro', 'how_to_play', 'block_intro', 'reminder', 'all_done'].forEach(name => {
    try {
      const a = loadAudio(name);
      a.muted = true;
      const p = a.play();
      if (p && p.then) p.then(() => { a.pause(); a.currentTime = 0; a.muted = false; })
                       .catch(() => { a.muted = false; });
    } catch (_) {}
  });
}

window.addEventListener('touchstart', unlockAudio, { once: true, passive: true, capture: true });
window.addEventListener('click',      unlockAudio, { once: true, capture: true });

// ============ visual rewards ============
function emitSparkles(card: Element, n = 14): void {
  const rect = card.getBoundingClientRect();
  const cx = rect.left + rect.width / 2;
  const cy = rect.top  + rect.height / 2;
  const colors = ['#ffd166', '#ff6f61', '#6ec1e4', '#6abf69', '#c084fc'];
  for (let i = 0; i < n; i++) {
    const s = document.createElement('div');
    s.className = 'sparkle';
    s.style.background = colors[Math.floor(Math.random() * colors.length)];
    s.style.left = (cx - 7) + 'px';
    s.style.top  = (cy - 7) + 'px';
    s.style.position = 'fixed';
    const angle = Math.random() * Math.PI * 2;
    const dist  = 80 + Math.random() * 100;
    s.style.setProperty('--dx', `${Math.cos(angle) * dist}px`);
    s.style.setProperty('--dy', `${Math.sin(angle) * dist}px`);
    document.body.appendChild(s);
    setTimeout(() => s.remove(), 1000);
  }
}
function bumpScore(score: number): void {
  const el = document.getElementById('score-val');
  if (!el) return;
  el.textContent = String(score);
  el.classList.remove('score-pop');
  void (el as any).offsetWidth;
  el.classList.add('score-pop');
}

// ============ experiment params ============
// Prolific appends PROLIFIC_PID, STUDY_ID and SESSION_ID to the study URL.
// Param names are case-sensitive and upper-case on their side.
// Prolific substitutes {{%PROLIFIC_PID%}} in the study URL. If someone opens
// the raw link, or substitution fails, the literal placeholder arrives
// instead — and since records upsert on participantID, every such visitor
// would overwrite the previous one. Treat anything template-shaped as absent.
function cleanProlificParam(v: string | null): string | null {
  if (!v) return null;
  const t = v.trim();
  if (!t || /[{}%]/.test(t) || t.toUpperCase() === 'NULL') return null;
  return t;
}
const PROLIFIC_PID  = cleanProlificParam(getURLParam('PROLIFIC_PID', null));
const PROLIFIC_STUDY = cleanProlificParam(getURLParam('STUDY_ID', null));
const PROLIFIC_SESSION = cleanProlificParam(getURLParam('SESSION_ID', null));
const IS_PROLIFIC = !!PROLIFIC_PID;

// Key the record on the Prolific ID when there is one, so a participant who
// refreshes mid-study upserts onto their own row instead of creating a second
// one, and so payment can be reconciled without a lookup table.
const PARTICIPANT_ID = PROLIFIC_PID
  || getURLParam('participantID', null)
  || ('kid_' + shortId(8));
const STUDY = getURLParam('study', IS_PROLIFIC ? 'things_kids_prolific' : 'things_kids_v1') as string;

// Where to send people when they finish. Prolific participants must land on
// their completion URL or they cannot be paid; pass it as ?completion_url=...
// (URL-encoded), or set the completion code with ?cc=XXXXXXXX.
// Adult determination has to come before the completion URL below: the exit
// target depends on it, and gating on IS_PROLIFIC instead sent any adult
// session without a usable Prolific ID (a ?consent=adult preview, or a raw
// unsubstituted study link) to the museum kiosk landing page.
const PROLIFIC_URL_SHAPE = /PROLIFIC_PID/i.test(window.location.search);
const CONSENT_MODE = (getURLParam('consent', null) ||
  ((IS_PROLIFIC || PROLIFIC_URL_SHAPE) ? 'adult' : 'kid')) as 'adult' | 'kid';
const IS_ADULT = CONSENT_MODE === 'adult';

const COMPLETION_CODE = getURLParam('cc', IS_ADULT ? 'CHO0PAQJ' : null);

// Which consent screen to show. Defaults to the adult IRB form for Prolific
// and the parental/kiosk screen otherwise; ?consent=adult or ?consent=kid
// forces either one so both can be previewed without faking a Prolific ID.

// Response lockout: ignore taps for this many ms after a trial appears.
// Adults on Prolific are paid per session and some will mash through; a
// short lockout makes that strictly slower than looking. Kids get 0 —
// a 3-year-old's slow deliberate tap should never be swallowed.
const LOCKOUT_MS = parseInt(
  getURLParam('lockout_ms', IS_ADULT ? '400' : '0') as string, 10);
const COMPLETION_URL = getURLParam('completion_url', null)
  || (COMPLETION_CODE ? `https://app.prolific.com/submissions/complete?cc=${COMPLETION_CODE}` : null);

// Save endpoint: defaults to a /submit relative to the current URL, which
// matches the lab nginx-prefix pattern (BASE_PATH/submit). Override with
// ?submit_url=https://... for cross-origin testing.
const SUBMIT_URL: string = getURLParam('submit_url', './submit') as string;
const SAVE_ENABLED: boolean = getURLParam('save', 'true') !== 'false';
// `?show_download=true` reveals a fallback "Download my data" button (dev mode).
const SHOW_DOWNLOAD: boolean = getURLParam('show_download', 'false') === 'true';

// No within-block reminder screens by default — block intros are enough,
// and the audio prompt plays at each block start so non-readers still get
// the rule. Pass ?reminder_every=20 to bring back periodic reminders.
const REMINDER_EVERY = parseInt(getURLParam('reminder_every', '0') as string, 10);
// Block-intro screens already serve as natural breaks, so default off.
// Pass ?break_every=20 to re-enable mid-block breaks.
const BREAK_EVERY    = parseInt(getURLParam('break_every', '0') as string, 10);

// Kiosk landing page — Stop button + post-session redirect target.
const EXIT_URL = getURLParam('exit_url', 'https://stanford-cogsci.org:8880/landing_page.html') as string;
const END_REDIRECT_MS = parseInt(getURLParam('end_redirect_ms', '8000') as string, 10);

// Wire up the persistent Stop button as soon as the script loads. It exists
// for kiosk staff to bail a child out; on the adult/Prolific version it would
// dump the participant on the museum landing page with no way back and no
// completion code, so it is removed entirely rather than hidden.
{
  const btn = document.getElementById('exit-btn') as HTMLButtonElement | null;
  if (btn) {
    if (CONSENT_MODE === 'adult') {
      btn.remove();
    } else {
      btn.addEventListener('click', () => { window.location.href = EXIT_URL; });
    }
  }
}

// Free-text comment from the debrief screen, saved with the session.
let DEBRIEF_COMMENT = '';

let CONSENT_INFO: { age: string | null; agreed: boolean } = { age: null, agreed: false };
// Which rotating block this child was assigned (banked manifests only).
let ASSIGNED_BLOCK: number | null = null;
// Which bank the block came from — 'adult' (40 trials) or 'child' (20).
let ASSIGNED_BANK: 'adult' | 'child' | null = null;
let SCORE = 0;

// ============ types ============
interface Trial {
  trial_id: string;
  tier: 'training' | 'warmup' | 'familiar' | 'novel' | 'catch';
  dataset: string;
  condition: string;
  n_objects: number;
  oddity_index: number;
  images: string[];
  human_avg_adult: number;
  rt_avg_adult?: number | null;
}

// HUD shows progress + score during trials only. Other screens (block
// intros, breaks, reminders, welcome, how-to-play, end) hide it so the
// fixed progress bar doesn't overlap their text.
function setHud(visible: boolean): void {
  const hud = document.getElementById('hud');
  if (hud) hud.style.display = visible ? 'flex' : 'none';
}

// ============ trial builder ============
function makeOddityTrial(
  t: Trial,
  trialNum: number,
  totalTrials: number,
  cueAudio: boolean = false,
): any {
  const order = t.images.map((_, i) => i);
  for (let i = order.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [order[i], order[j]] = [order[j], order[i]];
  }

  const stimulus = `
    <div class="kid-prompt">Find the one that's different<span class="sub">Tap the picture that's different.</span></div>
    <div class="kid-row" id="row-${t.trial_id}">
      ${order.map((origIdx, displayPos) => `
        <div class="kid-card" data-orig="${origIdx}" data-pos="${displayPos}">
          <img src="${t.images[origIdx]}" alt="object ${displayPos + 1}" />
        </div>`).join('')}
    </div>
  `;

  return {
    type: jsPsychHtmlKeyboardResponse,
    stimulus,
    choices: 'NO_KEYS',
    trial_duration: null,
    on_load: function () {
      ac();
      // Cue audio on the first trial of a tier that has no separate intro
      // screen (training, warmup) so kids who can't read still get the rule.
      if (cueAudio) playPrompt('block_intro');
      setHud(true);
      const fill = document.getElementById('prog-fill') as HTMLElement;
      const lbl  = document.getElementById('prog-label') as HTMLElement;
      if (fill) fill.style.width = `${100 * trialNum / totalTrials}%`;
      if (lbl)  lbl.textContent  = `${trialNum + 1} / ${totalTrials}`;

      const start = performance.now();
      const cards = document.querySelectorAll(`#row-${t.trial_id} .kid-card`);

      // Locked until LOCKOUT_MS has passed. `responded` replaces the old
      // { once: true }: with `once`, a tap during the lockout would remove
      // the listener even though we ignored it, killing that card for the
      // rest of the trial.
      let locked = LOCKOUT_MS > 0;
      let responded = false;
      if (locked) {
        const row = document.getElementById(`row-${t.trial_id}`);
        row?.classList.add('locked');
        setTimeout(() => {
          locked = false;
          row?.classList.remove('locked');
        }, LOCKOUT_MS);
      }

      cards.forEach((card) => {
        card.addEventListener('click', () => {
          if (locked || responded) return;
          responded = true;
          const rt = performance.now() - start;
          const chosenOrig = parseInt(card.getAttribute('data-orig')!, 10);
          const chosenPos  = parseInt(card.getAttribute('data-pos')!, 10);
          const correct    = chosenOrig === t.oddity_index;
          cards.forEach(c => c.classList.add('disabled'));
          card.classList.add(correct ? 'correct' : 'wrong');

          if (correct) {
            playChime();
            emitSparkles(card, 16);
            SCORE += 1;
            bumpScore(SCORE);
          } else {
            const rightCard = Array.from(cards).find(c => parseInt(c.getAttribute('data-orig')!, 10) === t.oddity_index);
            if (rightCard) setTimeout(() => rightCard.classList.add('correct'), 260);
          }

          (jsPsych as any).finishTrial({
            task: 'things_oddity',
            trial_id: t.trial_id, dataset: t.dataset, condition: t.condition, tier: t.tier,
            n_objects: t.n_objects,
            oddity_index_orig: t.oddity_index,
            chosen_orig_index: chosenOrig,
            chosen_display_pos: chosenPos,
            display_order: order,
            correct, rt,
            human_avg_adult: t.human_avg_adult,
            rt_avg_adult: t.rt_avg_adult ?? null,
            score_after: SCORE,
            lockout_ms: LOCKOUT_MS,
          });
        });
      });
    },
    data: { task_block: 'things_oddity', trial_id: t.trial_id, condition: t.condition },
  };
}

// ============ consent + age screen ============
function consentTrial(): any {
  return CONSENT_MODE === 'adult' ? consentTrialAdult() : consentTrialKid();
}

// ---- Adult consent: the IRB-approved form for study #811123, shown verbatim.
function consentTrialAdult(): any {
  const stimulus = `
    <div id="consent-adult">
      <h1 class="ca-title">${CONSENT_STUDY_TITLE}</h1>
      <p class="ca-sub">UC San Diego &middot; Study #${CONSENT_STUDY_NUMBER} &middot; Please read before taking part</p>
      <div class="ca-scroll" id="ca-scroll" tabindex="0">${consentHTML()}</div>
      <p class="ca-tools">
        <button type="button" class="ca-link" id="ca-download">Download a copy of this form</button>
      </p>
      <label class="ca-agree" for="ca-cb">
        <input id="ca-cb" type="checkbox" />
        <span>${CONSENT_AGREEMENT_LINE}</span>
      </label>
      <p class="ca-note" id="ca-note">Please read the form and tick the box to continue.</p>
    </div>
  `;
  return {
    type: jsPsychHtmlButtonResponse,
    stimulus,
    choices: ['Continue'],
    button_html: (c: string) =>
      `<button class="big-btn" id="consent-go" disabled style="opacity:0.45;cursor:not-allowed">${c}</button>`,
    on_load: function () {
      ac();
      // Prolific participants are adults by definition; no age grid is shown,
      // and precise age comes from Prolific's own demographics export.
      CONSENT_INFO.age = 'adult';
      const cb = document.getElementById('ca-cb') as HTMLInputElement;
      const note = document.getElementById('ca-note');
      cb.addEventListener('change', () => {
        CONSENT_INFO.agreed = cb.checked;
        const go = document.getElementById('consent-go') as HTMLButtonElement | null;
        if (!go) return;
        go.disabled = !cb.checked;
        go.style.opacity = cb.checked ? '1' : '0.45';
        go.style.cursor = cb.checked ? 'pointer' : 'not-allowed';
        if (note) note.style.visibility = cb.checked ? 'hidden' : 'visible';
      });
      document.getElementById('ca-download')?.addEventListener('click', () => {
        const blob = new Blob([consentPlainText()], { type: 'text/plain' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `consent_study_${CONSENT_STUDY_NUMBER}.txt`;
        a.click();
      });
    },
    data: { task: 'consent', consent_version: 'adult_irb_811123' },
    on_finish: function (data: any) {
      data.consent_age = CONSENT_INFO.age;
      data.consent_agreed = CONSENT_INFO.agreed;
    },
  };
}

// ---- Parental / museum-kiosk consent, unchanged.
function consentTrialKid(): any {
  const stimulus = `
    <div id="consent-wrap">
      <h1>Picture Detective!</h1>
      <img src="images/zorpie/zorpie_wave.gif" class="zorpie big" alt="Zorpie waves hello" />
      <p class="bell" style="font-size:32px;color:#444;margin:6px 0 0">Hi! I'm Zorpie!</p>

      <p class="bell" style="font-size:30px;margin:18px 0 8px">HOW OLD ARE YOU?</p>
      <div class="age-grid" id="age-grid">
        ${[2, 3, 4, 5, 6, 7, 8, 9, '10+', 'adult'].map(a => `
          <button class="age-btn" data-age="${a}">${a}</button>
        `).join('')}
      </div>

      <p class="agree-row">
        <label style="display:flex;align-items:center;gap:10px;cursor:pointer">
          <input id="agree-cb" type="checkbox" style="width:24px;height:24px" />
          <span>YOU CAN USE MY DATA</span>
        </label>
      </p>

      <details class="consent-text">
        <summary class="bell" style="cursor:pointer;font-size:18px;color:#666">Consent details (for parents/guardians)</summary>
        <p style="margin-top:12px">
          By proceeding, you and your child agree to participate in this research. Your child
          will be asked to play a short picture-matching game on this tablet/computer. No
          audio/video recording will occur and no identifying information will be collected.
          Your child's participation will take approximately 3–8 minutes, depending on their pace.
          The game data collected here will be used for research purposes by the
          UCSD Visual Learning Lab. There are no risks or benefits to participating: no
          identifying information will be collected, so you and your child's identity will
          remain anonymous. Your child can stop the game at any time or choose not to answer
          any question without penalty. For more information, email the UCSD lab at
          <i>vislearnlab@ucsd.edu</i>. If you are not satisfied with how this study is being
          conducted, or if you have any concerns, complaints, or general questions about the
          research or your rights as a participant, please contact the UCSD Human Research
          Protections Program at (858) 246-4777.
        </p>
      </details>

      <p style="font-size:15px;color:#777;margin-top:8px">Pick your age and check the box to continue.</p>
    </div>
  `;
  return {
    type: jsPsychHtmlButtonResponse,
    stimulus,
    choices: ["LET'S PLAY!"],
    button_html: (c: string) => `<button class="big-btn" id="consent-go" disabled style="opacity:0.45;cursor:not-allowed">${c}</button>`,
    on_load: function () {
      ac();
      // intro audio plays on the prior welcome screen, not here.
      const grid = document.getElementById('age-grid')!;
      const cb = document.getElementById('agree-cb') as HTMLInputElement;
      const refresh = () => {
        const go = document.getElementById('consent-go') as HTMLButtonElement | null;
        if (!go) return;
        const ok = !!CONSENT_INFO.age && cb.checked;
        go.disabled = !ok;
        go.style.opacity = ok ? '1' : '0.45';
        go.style.cursor  = ok ? 'pointer' : 'not-allowed';
      };
      grid.querySelectorAll('.age-btn').forEach((b) => {
        b.addEventListener('click', () => {
          grid.querySelectorAll('.age-btn').forEach(x => x.classList.remove('selected'));
          b.classList.add('selected');
          CONSENT_INFO.age = b.getAttribute('data-age');
          refresh();
        });
      });
      cb.addEventListener('change', () => {
        CONSENT_INFO.agreed = cb.checked;
        refresh();
      });
    },
    data: { task: 'consent', consent_version: 'parental_kiosk' },
    on_finish: function (data: any) {
      data.consent_age = CONSENT_INFO.age;
      data.consent_agreed = CONSENT_INFO.agreed;
    },
  };
}

// ============ block intros ============
// Each non-training block opens with a short Zorpie screen telling the
// kid what's coming next. Photos block also flags the n=4 layout.
// Block intros (only for the two test blocks: familiar, novel). Stripped
// to one phrase + Zorpie + audio. Audio plays automatically and the screen
// auto-advances when it ends.
function blockIntro(tier: string): any {
  if (tier !== 'mixed') return null;
  const id = `block-go-${tier}`;
  return {
    type: jsPsychHtmlButtonResponse,
    stimulus: `
      <div style="text-align:center; padding: 24px;">
        <img src="images/zorpie/zorpie_happy.gif" class="zorpie big" alt="" />
        <div class="bell" style="font-size:42px;color:#ff6f61;margin:18px 0 0">
          Tap the picture that's <b>different</b>!
        </div>
      </div>`,
    choices: [' '],
    button_html: (c: string) =>
      `<button class="big-btn" id="${id}" style="visibility:hidden">${c}</button>`,
    on_load: () => {
      setHud(false);
      const audio = playPrompt('block_intro');
      const advance = () => document.getElementById(id)?.click();
      audio.addEventListener('ended', advance, { once: true });
      setTimeout(advance, 8000);
    },
    data: { task: 'block_intro', tier },
  };
}

// ============ jsPsych init ============
const jsPsych = initJsPsych({
  show_progress_bar: false,
  on_finish: async function () {
    const all = jsPsych.data.get().values();
    const oddity = all.filter((d: any) => d.task === 'things_oddity');
    const summary = {
      participantID: PARTICIPANT_ID, study: STUDY,
      prolific: IS_PROLIFIC
        ? { pid: PROLIFIC_PID, study_id: PROLIFIC_STUDY, session_id: PROLIFIC_SESSION }
        : null,
      // True when the URL looked like a Prolific link but carried no usable
      // id — flags sessions that cannot be reconciled against a submission.
      prolific_id_missing: PROLIFIC_URL_SHAPE && !IS_PROLIFIC,
      consent: CONSENT_INFO,
      consent_version: CONSENT_MODE === 'adult' ? 'adult_irb_811123' : 'parental_kiosk',
      debrief_comment: DEBRIEF_COMMENT || null,
      assigned_block: ASSIGNED_BLOCK,
      assigned_bank: ASSIGNED_BANK,
      finishedAt: new Date().toISOString(),
      n_trials: oddity.length,
      n_correct: oddity.filter((d: any) => d.correct).length,
      mean_rt: oddity.length ? oddity.reduce((a: number, d: any) => a + d.rt, 0) / oddity.length : null,
      trials: oddity,
      ua: navigator.userAgent,
      screen: { w: screen.width, h: screen.height, dpr: window.devicePixelRatio },
    };

    document.body.innerHTML = `
      <div style="text-align:center; padding: 40px 24px; max-width: 760px; margin: 0 auto;">
        <img src="images/zorpie/zorpie_stars.gif" class="zorpie big" alt="Zorpie celebrates" />
        <div class="bell" style="font-size: 64px; color:#ff6f61;">Thank you!</div>
        <div style="font-size:28px; color:#444; margin-top: 18px;">
          ${IS_ADULT ? 'You&rsquo;ve finished the study.' : 'Great job playing the matching game!'}
        </div>
        <div id="save-status" style="margin-top:24px; font-size:15px; color:#888;">saving your answers…</div>
        <div id="prolific-code" style="display:none; margin-top:14px; font-size:16px; color:#444;"></div>
        ${IS_ADULT ? `
        <p class="end-downloads">
          <button type="button" class="ca-link" id="dl-consent">Download a copy of the consent form</button>
          <span class="sep">&middot;</span>
          <button type="button" class="ca-link" id="dl-responses">Download my responses</button>
        </p>` : ''}
        <div style="margin-top:24px;">
          <button class="big-btn" id="back-home">${IS_ADULT ? 'Return to Prolific' : 'Back to home'}</button>
        </div>
        <div id="dl-fallback" style="margin-top:18px; display:none;">
          <button class="big-btn warning" id="dl">Download my data</button>
          <div style="font-size:13px;color:#999;margin-top:6px">(in case the server is down)</div>
        </div>
      </div>`;

    setTimeout(playChime, 100); setTimeout(playChime, 400); setTimeout(playChime, 700);
    setTimeout(() => playPrompt('all_done'), 900);

    // Kiosk auto-returns to the landing page; Prolific participants go to
    // their completion URL instead, or they cannot be paid.
    // An adult session never returns to the museum kiosk. If no completion
    // URL could be built, stay put rather than navigating somewhere useless.
    const exitTarget = IS_ADULT ? COMPLETION_URL : EXIT_URL;
    const goHome = () => { if (exitTarget) window.location.href = exitTarget; };
    const homeBtn = document.getElementById('back-home');
    homeBtn?.addEventListener('click', goHome);

    if (IS_ADULT) {
      // Label is set in the template above, not patched here — patching left
      // a frame where an adult could read "Back to home", and home is the
      // museum kiosk.
      // No blind timer here. On the kiosk an early redirect costs nothing —
      // the next child just starts over. On Prolific it would race the POST
      // and lose the session, so the redirect is armed by the save handler
      // below once the data is actually stored.
    } else if (END_REDIRECT_MS > 0) {
      setTimeout(goHome, END_REDIRECT_MS);
    }

    if (IS_ADULT) {
      document.getElementById('dl-consent')?.addEventListener('click', () => {
        const blob = new Blob([consentPlainText()], { type: 'text/plain' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `consent_study_${CONSENT_STUDY_NUMBER}.txt`;
        a.click();
      });
      document.getElementById('dl-responses')?.addEventListener('click', () => {
        const blob = new Blob([JSON.stringify(summary, null, 2)], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `responses_${PARTICIPANT_ID}.json`;
        a.click();
      });
    }

    // Called once the save resolves, either way.
    function finishProlific(saved: boolean) {
      if (!IS_ADULT) return;
      const status = document.getElementById('save-status');
      if (status) {
        status.innerHTML = saved
          ? `&#10003; answers saved &mdash; returning to Prolific…`
          : `Your answers could not be saved automatically. Please download them below and message the researcher.`;
      }
      // Always show the completion code: if the redirect is blocked or the
      // participant closes the tab early, this is how they still get paid.
      const codeBox = document.getElementById('prolific-code');
      if (codeBox && COMPLETION_CODE) {
        codeBox.style.display = 'block';
        codeBox.innerHTML = `Completion code: <strong>${COMPLETION_CODE}</strong>`;
      }
      if (saved) setTimeout(goHome, 2500);
    }

    function showDownloadFallback(reason: string) {
      const status = document.getElementById('save-status');
      if (status) status.textContent = `couldn't reach the lab server (${reason}). You can save your answers below.`;
      const dl = document.getElementById('dl-fallback');
      if (dl) dl.style.display = 'block';
      const btn = document.getElementById('dl');
      if (btn) btn.addEventListener('click', () => {
        const blob = new Blob([JSON.stringify(summary, null, 2)], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `${PARTICIPANT_ID}.json`;
        a.click();
      });
    }

    if (SAVE_ENABLED) {
      try {
        const r = await fetch(SUBMIT_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ participantID: PARTICIPANT_ID, data: summary }),
          keepalive: true,
        });
        if (r.ok) {
          const status = document.getElementById('save-status');
          if (status) status.textContent = '✓ answers saved';
          finishProlific(true);
        } else {
          showDownloadFallback(`HTTP ${r.status}`);
          finishProlific(false);
        }
      } catch (e: any) {
        console.warn('save failed:', e);
        showDownloadFallback(String(e?.message || e).slice(0, 60));
        finishProlific(false);
      }
    } else {
      const status = document.getElementById('save-status');
      if (status) status.textContent = '(saving disabled via ?save=false)';
      finishProlific(false);
      if (SHOW_DOWNLOAD) showDownloadFallback('save disabled');
    }
    if (SHOW_DOWNLOAD) showDownloadFallback('dev mode');
  },
});

// Expose for headless tests (Playwright reaches in via jsPsych.data.get()).
(window as any).jsPsych = jsPsych;

async function main(): Promise<void> {
  bootSay('loading trial manifest…');
  // Two manifest shapes are supported. The flat {trials: [...]} form is the
  // original fixed set. The banked form — {intro, core, blocks} — is the
  // rotating design: every child does intro + core (comparable across
  // children), plus ONE randomly assigned block (benchmark breadth, which
  // accumulates across children). Only `active_blocks` are served, so the
  // bank can be built large now and opened up as the sample grows.
  type Banked = {
    meta?: { active_blocks?: number; active_adult_blocks?: number };
    intro?: Trial[]; core?: Trial[]; blocks?: Trial[][]; adult_blocks?: Trial[][];
  };
  let manifest: { trials?: Trial[] } & Banked;
  try {
    const r = await fetch('manifest.json');
    if (!r.ok) throw new Error('manifest.json HTTP ' + r.status);
    manifest = await r.json();
  } catch (err) {
    bootFail('Could not load manifest.json: ' + err);
    throw err;
  }

  let assignedBlock: number | null = null;
  let trials: Trial[];
  // Adults draw from adult_blocks (40 trials): they are much faster than
  // children and are here for item coverage, so doubling their rotating
  // trials halves the participants needed for the same per-item precision.
  // Children keep the 20-trial blocks — 51 trials is already the limit for
  // a 3-year-old. The two sets are built separately because child blocks
  // overlap each other heavily and cannot simply be concatenated.
  const useAdultBank = IS_ADULT && !!manifest.adult_blocks?.length;
  const pool = useAdultBank ? manifest.adult_blocks! : manifest.blocks;
  if (pool && pool.length) {
    const activeCount = useAdultBank
      ? (manifest.meta?.active_adult_blocks ?? pool.length)
      : (manifest.meta?.active_blocks ?? pool.length);
    const active = Math.max(1, Math.min(activeCount, pool.length));
    // ?block=N pins the block, for piloting a specific one.
    const forced = parseInt(getURLParam('block', '') as string, 10);
    assignedBlock = Number.isFinite(forced) && forced >= 0 && forced < active
      ? forced
      : Math.floor(Math.random() * active);
    trials = [
      ...(manifest.intro || []),
      ...(manifest.core || []),
      ...pool[assignedBlock],
    ];
    ASSIGNED_BLOCK = assignedBlock;
    ASSIGNED_BANK = useAdultBank ? 'adult' : 'child';
  } else {
    trials = manifest.trials || [];
  }
  const allImages = trials.flatMap(t => t.images);
  bootSay(`found ${trials.length} trials — preloading…`);
  setTimeout(bootDone, 300);

  const timeline: any[] = [];

  timeline.push({
    type: jsPsychPreload,
    images: [
      ...allImages,
      'images/zorpie/zorpie_wave.gif',
      'images/zorpie/zorpie_happy.gif',
      'images/zorpie/zorpie_stars.gif',
      'images/zorpie/zorpie_confused.gif',
    ],
    audio: ['intro', 'how_to_play', 'block_intro', 'reminder', 'all_done'].map(n => `${AUDIO_BASE}/${n}.m4a`),
    message: '<div style="text-align:center"><div class="bell" style="font-size:40px;color:#ff6f61">Loading the game…</div><div style="font-size:22px;color:#555">Get ready to find the one that is different!</div></div>',
    show_progress_bar: true,
  });

  // 1. Consent + age picker. The LET'S PLAY tap is the user gesture that
  // unlocks audio playback for the rest of the session — browsers block
  // audio on freshly loaded pages until the first interaction.
  timeline.push(consentTrial());

  // 1b. Adult instructions. The task itself is built for 3-10 year olds, so
  // it is worth saying plainly that the cartoon and the spoken prompts are
  // meant for children — otherwise adults read the tone as a mistake.
  if (CONSENT_MODE === 'adult') {
    timeline.push({
      type: jsPsychHtmlButtonResponse,
      stimulus: `
        <div class="adult-instructions">
          <h2>Before you start</h2>
          <p><b>Please turn your audio on so you can hear the instructions.</b></p>
          <p>These instructions are for children, so they might feel a little odd.</p>
          <p>Please complete all trials to the best of your ability.</p>
        </div>`,
      choices: ['Start'],
      button_html: (c: string) => `<button class="big-btn">${c}</button>`,
      on_load: () => { ac(); setHud(false); },
      data: { task: 'adult_instructions' },
    });
  }

  // 2. Welcome screen — just Zorpie waving. intro.m4a plays automatically
  // (audio is unlocked by the consent click) and the screen auto-advances
  // when the audio 'ended' event fires. Fallback: an 8s timeout in case the
  // event doesn't fire (some browsers eat it on slow loads).
  timeline.push({
    type: jsPsychHtmlButtonResponse,
    stimulus: `
      <div style="text-align:center; padding: 40px 24px;">
        <img src="images/zorpie/zorpie_wave.gif" class="zorpie big" alt="Zorpie waves hello" />
      </div>`,
    choices: [' '],  // hidden — kid waits for audio to finish
    button_html: (c: string) =>
      `<button class="big-btn" id="welcome-go" style="visibility:hidden">${c}</button>`,
    on_load: () => {
      ac();
      setHud(false);
      const audio = playPrompt('intro');
      const advance = () => document.getElementById('welcome-go')?.click();
      audio.addEventListener('ended', advance, { once: true });
      setTimeout(advance, 8000);
    },
    data: { task: 'welcome' },
  });

  // 2. How-to-play (interactive demo — kid taps the kitty to advance)
  timeline.push({
    type: jsPsychHtmlButtonResponse,
    stimulus: `
      <div class="howto-wrap">
        <img src="images/zorpie/zorpie_happy.gif" class="zorpie med" alt="" />
        <div class="bell howto-title">Let's play a game!</div>
        <div class="howto-body">
          Two pictures are the <b>same</b> 🐶 🐶<br/>
          One is <b>different</b> 🐱<br/>
          Tap the <b>different</b> one!
        </div>
        <div class="demo-row" id="howto-row">
          <div class="demo-card" data-role="dog">🐶</div>
          <div class="demo-card" data-role="dog">🐶</div>
          <div class="demo-card diff" data-role="cat">🐱</div>
        </div>
        <div id="howto-feedback" class="howto-feedback">
          ✨ Try it! Tap the kitty 🐱
        </div>
      </div>`,
    choices: ["I'm ready!"],
    button_html: (c: string) =>
      `<button class="big-btn" id="howto-go" disabled style="opacity:0.45;cursor:not-allowed">${c}</button>`,
    on_load: () => {
      setHud(false);
      playPrompt('how_to_play');
      const fb = document.getElementById('howto-feedback')!;
      const go = document.getElementById('howto-go') as HTMLButtonElement | null;
      let solved = false;
      document.querySelectorAll('#howto-row .demo-card').forEach((card) => {
        card.addEventListener('click', () => {
          const role = (card as HTMLElement).dataset.role;
          if (role === 'cat') {
            solved = true;
            playChime();
            emitSparkles(card, 18);
            card.classList.add('correct');
            fb.innerHTML = `🌟 <b>That's right!</b> You're a Picture Detective! 🌟`;
            (fb as HTMLElement).style.color = '#3aa53a';
            if (go) {
              go.disabled = false;
              go.style.opacity = '1';
              go.style.cursor = 'pointer';
            }
          } else if (!solved) {
            card.classList.add('wrong');
            setTimeout(() => card.classList.remove('wrong'), 400);
            fb.innerHTML = `Oops! That's a doggy 🐶. Find the one that's <b>different</b>!`;
            (fb as HTMLElement).style.color = '#993556';
          }
        });
      });
    },
  });

  // 3. Block-by-tier playback. Training and warmup are fixed at the start.
  // Familiar + novel + catch trials are then INTERLEAVED in a single
  // shuffled test block — avoids fatigue × tier confounds where, e.g.,
  // novel trials all land at the end of the session.
  const byTier: Record<string, Trial[]> = {};
  for (const t of trials) (byTier[t.tier] ||= []).push(t);

  const testTrials: Trial[] = [
    ...(byTier.familiar || []),
    ...(byTier.novel    || []),
  ];
  for (let i = testTrials.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [testTrials[i], testTrials[j]] = [testTrials[j], testTrials[i]];
  }

  // Catch trials are spread evenly rather than shuffled in with the rest.
  // A uniform shuffle regularly drops two or three of them back-to-back,
  // which reads as a run of trivially easy trials and wastes them as an
  // attention measure — they only tell you anything if they sample attention
  // across the whole session. Each is placed at random within its own even
  // slice, so spacing is enforced but position is still jittered.
  const catchTrials = byTier.catch || [];
  const interleaved: Trial[] = testTrials.slice();
  if (catchTrials.length) {
    const stride = (interleaved.length + catchTrials.length) / (catchTrials.length + 1);
    catchTrials.forEach((c, k) => {
      const centre = Math.round(stride * (k + 1));
      const jitter = Math.floor(Math.random() * 3) - 1;   // -1, 0, or +1
      const at = Math.max(1, Math.min(interleaved.length, centre + jitter));
      interleaved.splice(at, 0, c);
    });
  }

  type Block = { tier: string; trials: Trial[] };
  const blockOrder: Block[] = [
    ...(byTier.training ? [{ tier: 'training', trials: byTier.training }] : []),
    ...(byTier.warmup ? [{ tier: 'warmup', trials: byTier.warmup }] : []),
    ...(interleaved.length ? [{ tier: 'mixed', trials: interleaved }] : []),
  ];

  let trialIndex = 0;
  const totalTrials = trials.length;
  for (const block of blockOrder) {
    const { tier, trials: blockTrials } = block;
    // Training already follows the global "How to play" screen, so skip its intro.
    if (tier !== 'training') {
      const intro = blockIntro(tier);
      if (intro) timeline.push(intro);
    }
    for (let bi = 0; bi < blockTrials.length; bi++) {
      const t = blockTrials[bi];
      // Tiers without a separate intro screen (training, warmup) cue the
      // rule audio on the first trial of the block so non-readers know
      // when to start listening for instructions.
      const cueAudio = bi === 0 && (tier === 'training' || tier === 'warmup');
      timeline.push(makeOddityTrial(t, trialIndex, totalTrials, cueAudio));
      const completed = trialIndex + 1;
      const isLast = completed === totalTrials;
      const isBreak = !isLast && BREAK_EVERY > 0 && completed % BREAK_EVERY === 0;
      const isReminderOnly = !isLast && !isBreak && REMINDER_EVERY > 0 && completed % REMINDER_EVERY === 0;

      if (isBreak) {
        timeline.push({
          type: jsPsychHtmlButtonResponse,
          stimulus: `
            <div style="text-align:center;">
              <img src="images/zorpie/zorpie_happy.gif" class="zorpie big" alt="" />
              <div class="bell" style="font-size:44px;color:#6ec1e4;margin-top:8px">Wiggle break! 🤸</div>
              <div style="font-size:24px;color:#666;margin-top:8px">Stretch, wiggle, or take a sip 💧</div>
            </div>`,
          choices: ["I'm ready!"],
          button_html: (c: string) => `<button class="big-btn">${c}</button>`,
          on_load: () => setHud(false),
        });
      } else if (isReminderOnly) {
        timeline.push({
          type: jsPsychHtmlButtonResponse,
          stimulus: `
            <div style="text-align:center;">
              <img src="images/zorpie/zorpie_confused.gif" class="zorpie med" alt="" />
              <div class="bell" style="font-size:38px;color:#993556;margin-top:6px">You're doing great! 🌟</div>
              <div style="font-size:24px;color:#666;margin-top:6px;max-width:560px;margin-left:auto;margin-right:auto">
                Two are the same. One is different.<br/>Tap the one that's <b>different</b>!
              </div>
            </div>`,
          choices: ['Keep going!'],
          button_html: (c: string) => `<button class="big-btn secondary">${c}</button>`,
          on_load: () => { setHud(false); playPrompt('reminder'); },
        });
      }
      trialIndex++;
    }
  }

  // Final screen for adults: debrief plus an optional comment. It is the last
  // timeline entry so the comment is captured before jsPsych's on_finish
  // assembles and POSTs the payload — the comment ships in that same request
  // rather than needing a second one that could fail on its own.
  if (CONSENT_MODE === 'adult') {
    timeline.push({
      type: jsPsychHtmlButtonResponse,
      stimulus: `
        <div class="adult-instructions">
          <h2>Thanks for helping us with our study!</h2>
          <p>You can contact us at <a href="mailto:vislearnlab@ucsd.edu">vislearnlab@ucsd.edu</a>.</p>
          <p>If you have any comments, feel free to leave them below.</p>
          <textarea id="debrief-comment" rows="5"
            placeholder="Optional — anything you noticed, found confusing, or want to tell us."
            aria-label="Optional comments"></textarea>
          <p class="ai-note">Optional. Leave blank if you have nothing to add.</p>
        </div>`,
      choices: ['Finish'],
      button_html: (c: string) => `<button class="big-btn">${c}</button>`,
      on_load: () => { setHud(false); document.getElementById('debrief-comment')?.focus(); },
      on_finish: (data: any) => {
        const box = document.getElementById('debrief-comment') as HTMLTextAreaElement | null;
        DEBRIEF_COMMENT = (box?.value || '').trim().slice(0, 5000);
        data.debrief_comment = DEBRIEF_COMMENT;
      },
      data: { task: 'debrief' },
    });
  }

  jsPsych.run(timeline);
}

main();
