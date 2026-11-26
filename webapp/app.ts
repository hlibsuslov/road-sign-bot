// Mini App: sign library, learning (the same Leitner loop as the chat), timed tests, progress.
// Data: GET /api/catalog (public); everything personal goes through `Authorization: tma <initData>`,
// checked on the server. Answers to a test never reach the client before it is finished.
// Text goes through textContent only; nothing from data is parsed as markup.
import { createTma, parseStartParam } from './_kit/tma.ts';
import { renderScene, type SceneSpec } from './scene.ts';

type Lang = 'no' | 'en' | 'uk' | 'ru';
type Texts = Partial<Record<Lang, string>>;
type Category = { code: string; names: Texts; count: number };
type Sign = { id: string; number: string; category: string; shape: string | null; scale: number; names: Texts; descriptions: Texts; extra: Texts };
type Progress = { box: number; due: boolean; correct: number; wrong: number };
type PremiumStatus = { paywall: boolean; premium: boolean; active: boolean; expires_at: number | null; renews: boolean; price: number };
type ExamSummary = { correct: number; total: number; finished_at: number; passed: boolean };
type Me = {
  registered: boolean; study_language?: Lang; translation_language?: Lang | 'none';
  mastered_box?: number; max_box?: number; answered?: number; correct?: number; streak?: number;
  progress?: Record<string, Progress>; pool?: number; premium?: PremiumStatus; exams?: ExamSummary[];
  profile?: Profile; today?: number;
};
type Profile = { first_name: string | null; username: string | null; member_since: number; licence_class: string;
  exam_date: string | null; daily_goal: number; reminders: boolean; timezone: string | null };
type Topic = { id: string; icon: string; kind: 'signs' | 'questions'; names: Texts; summary: Texts; count: number; solved: number };
type TheoryIndex = { classes: Record<string, Texts>; licence_class: string; topics: Topic[] };
type Question = { id: string; topic: string; type: 'single' | 'multi'; difficulty: number; image: (SceneSpec | { sign: string }) | null;
  text: Texts; options: { id: string; text: Texts }[] };
type Verdict = { correct: boolean; correct_ids: string[]; explanation: Texts; source: string };
type Step = { mode: 'review'; sign_id: string; options: string[]; box: number }
  | { mode: 'new'; sign_id: string }
  | { mode: 'done'; queued: number; next_in: number | null };
type Exam = { exam_id: string; seconds: number; pass_ratio: number; questions: { n: number; image: string; scale: number; options: string[] }[] };
type ExamResult = { correct: number; total: number; passed: boolean; timed_out: boolean; items: { sign_id: string; ok: boolean; correct: string; chosen: string | null }[] };
type Tab = 'signs' | 'study' | 'exam' | 'progress';

const tma = createTma();
const $ = (id: string) => document.getElementById(id) as HTMLElement;
const ICONS = '_kit/icons.svg';
const EXAM_SIZES = [10, 20, 45];

let categories: Category[] = [];
let signs: Sign[] = [];
let byId = new Map<string, Sign>();
let me: Me = { registered: false };
let tab: Tab = 'signs';
let category = 'all';
let query = '';
let examSize = 20;
let theoryIndex: TheoryIndex | null = null;
const tabHistory: Tab[] = [];   // Telegram's Back walks back through the tabs the user opened

const studyLang = (): Lang => me.study_language ?? 'no';
const transLang = (): Lang | null => {
  const t = me.translation_language;
  return t && t !== 'none' && t !== studyLang() ? t : null;
};
const text = (t: Texts, lang: Lang | null = studyLang()) => (lang && t[lang]) || t.no || t.en || '';
const categoryName = (code: string) => text(categories.find((c) => c.code === code)?.names ?? {}, 'uk');
const plural = (n: number, one: string, few: string, many: string) =>
  n % 10 === 1 && n % 100 !== 11 ? one : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? few : many;
function duration(seconds: number): string {
  const m = Math.round(seconds / 60);
  if (m < 60) return `${Math.max(1, m)} хв`;
  const hrs = Math.round(m / 60);
  return hrs < 24 ? `${hrs} год` : `${Math.round(hrs / 24)} дн`;
}

/* ---------------------------------------------------------------- DOM helpers */
type Kid = Node | string | null | false;
function h(tag: string, attrs: Record<string, string | boolean | EventListener> = {}, ...kids: Kid[]): HTMLElement {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, '');
    else if (v !== false) el.setAttribute(k, v);
  }
  for (const kid of kids) if (kid) el.append(kid);
  return el;
}
function icon(name: string): SVGSVGElement {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'tma-icon'); svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', `${ICONS}#i-${name}`);
  svg.append(use);
  return svg;
}
const on = (fn: (e: Event) => void) => fn as EventListener;
/** Telegram Stars are drawn as the kit's SVG glyph, never as an emoji character. */
function starGlyph(): SVGSVGElement {
  const svg = icon('stars-gold');
  svg.setAttribute('class', 'tma-star');
  return svg;
}
/** Every sign sits in the same square; --d (utils.sign_scale on the server) evens out shapes. */
const artBox = (src: string, scale: number, alt: string, hero = false) =>
  h('div', { class: hero ? 'sign-art is-hero' : 'sign-art', style: `--d:${scale}` },
    h('img', { src, alt, decoding: 'async', loading: hero ? 'eager' : 'lazy' }));
const art = (s: Sign, hero = false) =>
  artBox(hero ? `signs/${s.id}.webp` : `signs/thumb/${s.id}.webp`, s.scale ?? 0.8, hero ? `Знак ${s.number}: ${text(s.names)}` : '', hero);
function placeholder(title: string, body: string, ...extra: Kid[]): HTMLElement {
  return h('div', { class: 'tma-placeholder' },
    h('p', { class: 'tma-placeholder__title' }, title), h('p', { class: 'tma-placeholder__text' }, body), ...extra);
}
let toastTimer = 0;
function toast(message: string): void {
  const s = $('snackbar'); s.textContent = message; s.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => { s.hidden = true; }, 2600);
}

function status(s: Sign): HTMLElement | null {
  const p = me.progress?.[s.id];
  if (!p) return null;
  const mastered = p.box >= (me.mastered_box ?? 4);
  const label = mastered ? 'Вивчено' : p.due ? 'Час повторити' : `Рівень ${p.box}`;
  return h('span', { class: mastered ? 'sign-status is-mastered' : 'sign-status' }, label);
}

/* ---------------------------------------------------------------- API */
class ApiErr extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string) { super(code); this.status = status; this.code = code; }
}
async function api<T>(path: string, init: { method?: string; body?: unknown; auth?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (init.auth !== false) headers.Authorization = `tma ${tma.tg?.initData ?? ''}`;
  if (init.body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetch(path, { method: init.method ?? 'GET', headers, body: init.body === undefined ? undefined : JSON.stringify(init.body) });
  if (!res.ok) {
    let code = `http_${res.status}`;
    try { code = (await res.json()).error ?? code; } catch { /* plain-text error */ }
    throw new ApiErr(res.status, code);
  }
  return res.json() as Promise<T>;
}
const refreshMe = async () => { if (tma.inTelegram) me = await api<Me>('/api/me').catch(() => me); };

/* ---------------------------------------------------------------- navigation */
function setTab(t: Tab): void {
  tab = t;
  for (const b of document.querySelectorAll<HTMLButtonElement>('[data-tab]')) b.setAttribute('aria-selected', String(b.dataset.tab === t));
  tma.mainButton(null); tma.secondaryButton(null);
  renderRoot();
  window.scrollTo(0, 0);
}
function syncTabBack(): void {
  tma.nav.pop('tab');
  if (tabHistory.length) tma.nav.push({ id: 'tab', kind: 'screen', onBack: backTab });
}
function backTab(): void {
  const prev = tabHistory.pop();
  if (prev) setTab(prev);
  syncTabBack();
}
for (const b of document.querySelectorAll<HTMLButtonElement>('[data-tab]')) {
  b.onclick = () => {
    if (b.dataset.tab === tab) return;
    tma.haptic.select();
    tabHistory.push(tab);
    setTab(b.dataset.tab as Tab);
    syncTabBack();
  };
}
/** Full-screen flows (sign card, learning session, test, results) share one screen and Telegram's Back. */
function openScreen(onBack: () => void): HTMLElement {
  const el = $('detail');
  el.replaceChildren();
  $('root').hidden = true; el.hidden = false; $('tabbar').hidden = true;
  tma.nav.pop('screen');
  tma.nav.push({ id: 'screen', kind: 'screen', onBack });
  window.scrollTo(0, 0);
  return el;
}
function closeScreen(): void {
  tma.nav.pop('screen');
  tma.mainButton(null); tma.secondaryButton(null); tma.closingConfirmation(false);
  $('detail').hidden = true; $('root').hidden = false; $('tabbar').hidden = false;
  $('root').classList.add('is-back');
  renderRoot();
}

/* ---------------------------------------------------------------- roots */
function renderRoot(): void {
  const root = $('root');
  root.removeAttribute('aria-busy');
  const screens: Record<Tab, () => Kid[]> = { signs: libraryScreen, study: studyRoot, exam: examRoot, progress: progressScreen };
  root.replaceChildren(...screens[tab]());
  if (tab === 'signs') renderList();
}
const largeTitle = (title: string) => h('header', { class: 'tma-header' }, h('h1', { class: 'tma-large-title' }, title));

/** Gate for personal sections: outside Telegram, before onboarding, or before Premium. */
function gate(): Kid[] | null {
  if (!tma.inTelegram) return [placeholder('Відкрийте з Telegram', 'Навчання і тести працюють, коли застосунок відкрито кнопкою «Знаки» в боті.')];
  if (!me.registered) return [placeholder('Спершу налаштуйте бота', 'Відкрийте /start у чаті й оберіть мови — потім повертайтеся сюди.')];
  if (me.premium && !me.premium.premium) return paywall();
  return null;
}

/* ---------------------------------------------------------------- library */
function libraryScreen(): Kid[] {
  const search = h('input', { type: 'search', placeholder: 'Назва або номер', 'aria-label': 'Пошук знака', value: query }) as HTMLInputElement;
  search.oninput = () => { query = search.value.trim().toLowerCase(); renderList(); };
  const chips = h('div', { class: 'tma-scroll-x', role: 'group', 'aria-label': 'Категорія', style: 'margin-top:var(--tma-s3)' },
    ...[{ code: 'all', label: 'Усі' }, ...categories.map((c) => ({ code: c.code, label: text(c.names, 'uk') }))].map((c) =>
      h('button', { class: 'tma-chip', type: 'button', 'aria-pressed': String(category === c.code),
        onclick: on(() => { if (category !== c.code) { category = c.code; tma.haptic.select(); renderRoot(); } }) }, c.label)));
  return [largeTitle('Дорожні знаки'), h('label', { class: 'tma-search' }, icon('search'), search), chips,
    h('div', { id: 'list', style: 'margin-top:var(--tma-gap-section)' })];
}
function matches(s: Sign): boolean {
  if (category !== 'all' && s.category !== category) return false;
  if (!query) return true;
  return s.number.startsWith(query) || Object.values(s.names).some((n) => (n ?? '').toLowerCase().includes(query));
}
function renderList(): void {
  const list = document.getElementById('list');
  if (!list) return;
  const items = signs.filter(matches);
  if (!items.length) {
    list.replaceChildren(placeholder('Нічого не знайдено', 'Спробуйте інше слово або номер знака.',
      h('button', { class: 'tma-btn is-tonal', type: 'button', onclick: on(() => { query = ''; category = 'all'; renderRoot(); }) }, 'Скинути пошук')));
    return;
  }
  list.replaceChildren(
    h('p', { class: 'tma-footnote', style: 'margin:0 0 var(--tma-s3)', 'aria-live': 'polite' }, `Знаків: ${items.length}`),
    h('div', { class: 'sign-grid' }, ...items.map((s) =>
      h('a', { class: 'sign-tile', href: `#sign-${s.id}`, onclick: on((e) => { e.preventDefault(); tma.haptic.tap(); openSign(s); }) },
        art(s), h('span', { class: 'tma-meta' }, s.number), h('span', { class: 'sign-tile__name' }, text(s.names)), status(s)))));
}
function openSign(s: Sign): void {
  const el = openScreen(closeScreen);
  const trans = transLang();
  const extra = text(s.extra);
  const about = h('p', { class: 'tma-clamp-3', style: 'margin:0' }, extra);
  const p = me.progress?.[s.id];
  const similar = signs.filter((x) => x.category === s.category && x.id !== s.id).slice(0, 8);
  el.append(
    art(s, true),
    h('h1', { class: 'tma-title2', style: 'text-align:center' }, text(s.names)),
    trans ? h('p', { class: 'tma-subhead tma-hint', style: 'text-align:center;margin:var(--tma-s1) 0 0' }, text(s.names, trans)) : '',
    h('div', { class: 'tma-stack', style: 'margin-top:var(--tma-gap-section)' },
      h('section', { class: 'tma-card' }, h('p', { style: 'margin:0' }, text(s.descriptions)),
        trans ? h('p', { class: 'tma-hint', style: 'margin:0' }, text(s.descriptions, trans)) : ''),
      extra ? h('section', { class: 'tma-card', 'aria-labelledby': 'about-h' },
        h('h2', { class: 'tma-headline', id: 'about-h', style: 'margin:0' }, 'Пояснення'), about,
        h('button', { class: 'tma-btn is-plain', type: 'button', onclick: on((e) => { about.classList.remove('tma-clamp-3'); (e.currentTarget as HTMLElement).remove(); }) }, 'Читати повністю')) : '',
      h('dl', { class: 'tma-kv' },
        h('div', {}, h('dt', {}, 'Номер'), h('dd', {}, s.number)),
        h('div', {}, h('dt', {}, 'Категорія'), h('dd', {}, categoryName(s.category))),
        p ? h('div', {}, h('dt', {}, 'Відповіді'), h('dd', {}, `${p.correct} правильно · ${p.wrong} помилок`)) : ''),
      similar.length ? h('section', { class: 'tma-section', 'aria-labelledby': 'sim-h' },
        h('h2', { class: 'tma-section__header', id: 'sim-h' }, 'Ще в цій категорії'),
        h('div', { class: 'tma-carousel', style: '--x:0' }, ...similar.map((x) =>
          h('a', { class: 'sign-tile', href: `#sign-${x.id}`, style: 'flex:0 0 30%', onclick: on((e) => { e.preventDefault(); tma.haptic.tap(); openSign(x); }) },
            art(x), h('span', { class: 'sign-tile__name' }, text(x.names)))))) : ''));
}

/* ---------------------------------------------------------------- premium paywall */
function paywall(): Kid[] {
  const price = me.premium?.price ?? 50;
  tma.mainButton({ text: `Оформити за ${price} ${plural(price, 'зірку', 'зірки', 'зірок')} на місяць`, onClick: buyPremium });
  return [h('section', { class: 'tma-card' },
    h('h2', { class: 'tma-title3', style: 'margin:0' }, 'Навчання і тести — у Преміумі'),
    h('ul', { class: 'tma-checks' },
      h('li', {}, 'Навчання тут, у застосунку: картки, квізи, інтервальні повторення'),
      h('li', {}, 'Тести як на teoriprøven: таймер, бал, розбір помилок'),
      h('li', {}, 'Той самий прогрес, що й у чаті')),
    h('p', { class: 'tma-headline', style: 'margin:0;display:flex;align-items:center;gap:6px' }, starGlyph(), `${price} ${plural(price, 'зірка', 'зірки', 'зірок')} Telegram на місяць`),
    h('p', { class: 'tma-footnote', style: 'margin:0' }, 'Продовжується щомісяця. Скасувати можна будь-коли в боті: /premium.'))];
}
async function buyPremium(): Promise<void> {
  try {
    const { link } = await api<{ link: string }>('/api/premium/invoice', { method: 'POST', body: {} });
    const result = await tma.pay(link);
    if (result === 'paid') {
      tma.haptic.success();
      toast('Оплату отримано. Відкриваємо доступ…');
      for (let i = 0; i < 8 && !me.premium?.premium; i++) {  // the bot applies successful_payment
        await new Promise((r) => setTimeout(r, 1500));
        await refreshMe();
      }
      renderRoot();
    } else if (result === 'failed') {
      toast('Оплата не пройшла. Спробуйте ще раз.');
    } else if (result === 'unsupported') {
      toast('Оновіть Telegram або оформіть у чаті: /premium');
    }
  } catch (e) {
    if (e instanceof ApiErr && e.code === 'not_needed') { await refreshMe(); renderRoot(); return; }
    toast('Не вдалося створити рахунок. Спробуйте ще раз.');
  }
}

/* ---------------------------------------------------------------- learning */
function studyRoot(): Kid[] {
  const blocked = gate();
  if (blocked) return [largeTitle('Навчання'), ...blocked];
  const due = Object.values(me.progress ?? {}).filter((p) => p.due).length;
  const pool = me.pool ?? signs.length;
  const known = Object.keys(me.progress ?? {}).length;
  tma.mainButton({ text: due ? `Картки · ${due} до повторення` : 'Картки зі знаками', onClick: () => openSwipe() });
  tma.secondaryButton({ text: 'Квіз з варіантами', onClick: () => openStudy() });
  const topics = h('ul', { class: 'tma-list' }, h('li', {}, h('p', { class: 'tma-hint', style: 'margin:0;padding:var(--tma-s3) var(--tma-s4)' }, 'Завантаження тем…')));
  void loadTopics(topics);
  return [largeTitle('Навчання'),
    h('section', { class: 'tma-card' },
      h('p', { class: 'tma-headline', style: 'margin:0' }, due ? `${due} ${plural(due, 'знак чекає', 'знаки чекають', 'знаків чекають')} на повторення` : 'Повторень знаків на зараз немає'),
      h('p', { class: 'tma-hint', style: 'margin:0' }, `У добірці ${pool} ${plural(pool, 'знак', 'знаки', 'знаків')}, ви вже бачили ${known}. Спершу повторення, потім нові знаки.`)),
    h('section', { class: 'tma-section', 'aria-labelledby': 'topics-h', style: 'margin-top:var(--tma-gap-section)' },
      h('h2', { class: 'tma-section__header', id: 'topics-h' }, 'Теорія за темами'), topics),
    h('p', { class: 'tma-footnote', style: 'padding:0 var(--tma-s4)' }, 'Прогрес спільний із чатом. Категорія прав — у розділі «Прогрес».')];
}

async function loadTopics(list: HTMLElement): Promise<void> {
  try {
    theoryIndex = await api<TheoryIndex>('/api/theory');
  } catch {
    list.replaceChildren(h('li', {}, h('p', { class: 'tma-hint', style: 'margin:0;padding:var(--tma-s3) var(--tma-s4)' }, 'Теми не завантажились. Відкрийте розділ ще раз.')));
    return;
  }
  list.replaceChildren(...theoryIndex.topics.map((t) => h('li', {}, h('button', { class: 'tma-cell is-2', type: 'button',
    onclick: on(() => { tma.haptic.tap(); if (t.kind === 'signs') openStudy(); else void openTheory(t); }) },
    h('span', { class: 'topic-icon' }, icon(t.icon)),
    h('span', { class: 'tma-cell__body' }, h('span', { class: 'tma-cell__title' }, text(t.names, 'uk')),
      h('span', { class: 'tma-cell__subtitle' }, text(t.summary, 'uk'))),
    h('span', { class: 'tma-cell__after' }, t.kind === 'signs' ? `${signs.length}` : `${t.solved}/${t.count}`)))));
}

/* ---------------------------------------------------------------- theory practice */
function questionImage(q: Question): Kid {
  if (!q.image) return '';
  if ('sign' in q.image) {
    const s = byId.get(q.image.sign);
    return s ? art(s, true) : '';
  }
  return h('div', { class: 'scene-box' }, renderScene(q.image, 'Схема ситуації на дорозі'));
}

async function openTheory(topic: Topic): Promise<void> {
  let questions: Question[];
  try {
    questions = (await api<{ questions: Question[] }>(`/api/theory/${encodeURIComponent(topic.id)}`)).questions;
  } catch (e) {
    if (e instanceof ApiErr && e.code === 'premium_required') { await refreshMe(); renderRoot(); return; }
    toast('Не вдалося відкрити тему. Спробуйте ще раз.');
    return;
  }
  const el = openScreen(async () => { await refreshMe(); closeScreen(); });
  let i = 0;
  let right = 0;
  const counter = h('p', { class: 'tma-footnote', style: 'text-align:center;margin:0', 'aria-live': 'polite' });
  const body = h('div', {});
  el.append(h('p', { class: 'tma-tag', style: 'text-align:center;margin:var(--tma-s2) 0 0' }, text(topic.names, 'uk')), counter, body);

  function draw(): void {
    tma.mainButton(null);
    if (i >= questions.length) {
      counter.textContent = '';
      body.replaceChildren(placeholder(`${right} з ${questions.length} правильно`,
        right === questions.length ? 'Тему пройдено без помилок.' : 'Питання з помилками повернуться першими наступного разу.'));
      tma.mainButton({ text: 'Готово', onClick: async () => { await refreshMe(); closeScreen(); } });
      return;
    }
    const q = questions[i];
    counter.textContent = `Питання ${i + 1} з ${questions.length}`;
    const trans = transLang();
    const picked = new Set<string>();
    const buttons = q.options.map((o) => h('button', { class: 'quiz-option', type: 'button', 'data-id': o.id, 'aria-pressed': 'false' }, text(o.text)) as HTMLButtonElement);
    const feedback = h('div', { 'aria-live': 'polite' });
    body.replaceChildren(
      questionImage(q),
      h('h1', { class: 'tma-title3', style: 'margin:var(--tma-s3) 0 0' }, text(q.text)),
      trans ? h('p', { class: 'tma-hint', style: 'margin:var(--tma-s1) 0 0' }, text(q.text, trans)) : '',
      q.type === 'multi' ? h('p', { class: 'tma-footnote', style: 'margin:var(--tma-s1) 0 0' }, 'Оберіть усі правильні відповіді') : '',
      h('div', { class: 'quiz-options', role: 'group', 'aria-label': 'Варіанти відповіді' }, ...buttons),
      feedback);

    async function check(): Promise<void> {
      for (const b of buttons) b.disabled = true;
      let v: Verdict;
      try {
        v = await api<Verdict>('/api/theory/answer', { method: 'POST', body: { question_id: q.id, chosen: [...picked] } });
      } catch {
        for (const b of buttons) b.disabled = false;
        toast('Відповідь не збережено. Спробуйте ще раз.');
        return;
      }
      if (v.correct) right++;
      for (const b of buttons) {
        const id = b.dataset.id ?? '';
        if (v.correct_ids.includes(id)) { b.classList.add('is-correct'); b.prepend(h('span', { class: 'quiz-mark' }, 'Правильно · ')); }
        else if (picked.has(id)) { b.classList.add('is-wrong'); b.prepend(h('span', { class: 'quiz-mark' }, 'Ваша відповідь · ')); }
      }
      if (v.correct) tma.haptic.success(); else tma.haptic.error();
      feedback.replaceChildren(h('section', { class: 'tma-card', style: 'margin-top:var(--tma-s4)' },
        h('p', { class: 'tma-headline', style: 'margin:0' }, v.correct ? 'Правильно' : 'Неправильно'),
        h('p', { style: 'margin:0' }, text(v.explanation)),
        trans ? h('p', { class: 'tma-hint', style: 'margin:0' }, text(v.explanation, trans)) : '',
        h('p', { class: 'tma-footnote', style: 'margin:0' }, `Джерело: ${v.source}`)));
      tma.mainButton({ text: i < questions.length - 1 ? 'Далі' : 'Завершити тему', onClick: () => { i++; draw(); window.scrollTo(0, 0); } });
    }

    for (const b of buttons) {
      b.onclick = () => {
        const id = b.dataset.id ?? '';
        if (q.type === 'single') { picked.add(id); b.classList.add('is-picked'); void check(); return; }
        if (picked.has(id)) picked.delete(id); else picked.add(id);
        b.setAttribute('aria-pressed', String(picked.has(id)));
        b.classList.toggle('is-picked', picked.has(id));
        tma.haptic.select();
        tma.mainButton(picked.size ? { text: 'Перевірити', onClick: () => void check() } : null);
      };
    }
  }
  draw();
}

function openStudy(): void {
  const session = { answered: 0, correct: 0 };
  const el = openScreen(closeScreen);
  const counter = h('p', { class: 'tma-footnote', 'aria-live': 'polite', style: 'text-align:center;margin:0' });
  const body = h('div', {});
  el.append(counter, body);
  const drawCounter = () => { counter.textContent = session.answered ? `Відповідей: ${session.answered} · правильно ${session.correct}` : ''; };

  async function next(early = false): Promise<void> {
    tma.mainButton(null); tma.secondaryButton(null);
    body.replaceChildren(h('p', { class: 'tma-hint', style: 'text-align:center' }, 'Завантаження…'));
    let step: Step;
    try {
      step = await api<Step>(`/api/study/next${early ? '?early=1' : ''}`);
    } catch (e) {
      if (e instanceof ApiErr && e.code === 'premium_required') { await refreshMe(); closeScreen(); return; }
      body.replaceChildren(placeholder('Не вдалося завантажити', 'Перевірте з’єднання.',
        h('button', { class: 'tma-btn is-tonal', type: 'button', onclick: on(() => void next(early)) }, 'Спробувати ще раз')));
      return;
    }
    const s = 'sign_id' in step ? byId.get(step.sign_id) : undefined;
    if (step.mode === 'new' && s) intro(s);
    else if (step.mode === 'review' && s) quiz(s, step.options, step.box);
    else done(step.mode === 'done' ? step : { mode: 'done', queued: 0, next_in: null });
    window.scrollTo(0, 0);
  }

  function intro(s: Sign): void {
    const trans = transLang();
    body.replaceChildren(
      h('p', { class: 'tma-tag', style: 'text-align:center;margin:var(--tma-s2) 0 0' }, 'Новий знак'),
      art(s, true),
      h('h1', { class: 'tma-title2', style: 'text-align:center' }, text(s.names)),
      trans ? h('p', { class: 'tma-subhead tma-hint', style: 'text-align:center;margin:var(--tma-s1) 0 0' }, text(s.names, trans)) : '',
      h('section', { class: 'tma-card', style: 'margin-top:var(--tma-gap-section)' },
        h('p', { style: 'margin:0' }, text(s.descriptions)),
        trans ? h('p', { class: 'tma-hint', style: 'margin:0' }, text(s.descriptions, trans)) : ''));
    tma.mainButton({ text: 'Далі', onClick: async () => { await api('/api/study/seen', { method: 'POST', body: { sign_id: s.id } }); tma.haptic.tap(); await next(); } });
    tma.secondaryButton({ text: 'Я вже знаю цей знак', onClick: async () => { await api('/api/study/known', { method: 'POST', body: { sign_id: s.id } }); tma.haptic.tap(); await next(); } });
  }

  function quiz(s: Sign, options: string[], box: number): void {
    const buttons = options.map((id) => h('button', { class: 'quiz-option', type: 'button', 'data-id': id }, text(byId.get(id)?.names ?? {})) as HTMLButtonElement);
    const feedback = h('div', { 'aria-live': 'polite' });
    body.replaceChildren(
      art(s, true),
      h('h1', { class: 'tma-title3', style: 'text-align:center;margin:0' }, 'Що означає цей знак?'),
      box ? h('p', { class: 'tma-footnote', style: 'text-align:center;margin:var(--tma-s1) 0 0' }, `Повторення · рівень ${box} з ${me.max_box ?? 6}`) : '',
      h('div', { class: 'quiz-options', role: 'group', 'aria-label': 'Варіанти відповіді' }, ...buttons),
      feedback);
    for (const b of buttons) {
      b.onclick = async () => {
        for (const x of buttons) x.disabled = true;
        b.classList.add('is-picked');
        let res: { correct: boolean; correct_id: string; box: number; mastered_now: boolean; next_in: number };
        try {
          res = await api('/api/study/answer', { method: 'POST', body: { sign_id: s.id, chosen: b.dataset.id } });
        } catch {
          for (const x of buttons) x.disabled = false;
          b.classList.remove('is-picked');
          toast('Відповідь не збережено. Спробуйте ще раз.');
          return;
        }
        session.answered++; if (res.correct) session.correct++;
        drawCounter();
        for (const x of buttons) {
          if (x.dataset.id === res.correct_id) { x.classList.add('is-correct'); x.prepend(h('span', { class: 'quiz-mark' }, 'Правильно · ')); }
          else if (x === b) { x.classList.add('is-wrong'); x.prepend(h('span', { class: 'quiz-mark' }, 'Ваша відповідь · ')); }
        }
        if (res.correct) tma.haptic.success(); else tma.haptic.error();
        feedback.replaceChildren(h('section', { class: 'tma-card', style: 'margin-top:var(--tma-s4)' },
          h('p', { class: 'tma-headline', style: 'margin:0' }, res.correct
            ? (res.mastered_now ? 'Правильно — знак вивчено' : `Правильно · наступне повторення через ${duration(res.next_in)}`)
            : 'Неправильно · цей знак повториться за кілька хвилин'),
          h('p', { class: 'tma-hint', style: 'margin:0' }, text(s.descriptions))));
        tma.mainButton({ text: 'Далі', onClick: () => next() });
      };
    }
  }

  function done(step: { queued: number; next_in: number | null }): void {
    body.replaceChildren(placeholder('На зараз усе',
      step.next_in != null ? `Наступне повторення через ${duration(step.next_in)}. Можна повторити раніше.` : 'Усі знаки з добірки пройдено.',
      step.queued ? h('button', { class: 'tma-btn is-tonal', type: 'button', onclick: on(() => void next(true)) }, 'Повторити зараз') : ''));
    tma.mainButton({ text: 'Готово', onClick: async () => { await refreshMe(); closeScreen(); } });
  }

  drawCounter();
  void next();
}

/* ---------------------------------------------------------------- swipe cards */
function openSwipe(): void {
  const el = openScreen(async () => { await refreshMe(); closeScreen(); });
  let known = 0, unknown = 0;
  const counter = h('p', { class: 'tma-footnote', style: 'text-align:center;margin:0', 'aria-live': 'polite' });
  const stage = h('div', { class: 'swipe-stage' });
  const hint = h('p', { class: 'tma-footnote', style: 'text-align:center' }, 'Торкніться картки, щоб перевернути. Вправо — знаю, вліво — ще ні.');
  el.append(counter, stage, hint);
  const draw = () => { counter.textContent = `Знаю ${known} · ще вчу ${unknown}`; };

  async function rate(s: Sign, isKnown: boolean, card: HTMLElement, isNew: boolean): Promise<void> {
    card.classList.add(isKnown ? 'is-gone-right' : 'is-gone-left');
    if (isKnown) { known++; tma.haptic.success(); } else { unknown++; tma.haptic.warning(); }
    draw();
    try {
      if (isNew) await api('/api/study/seen', { method: 'POST', body: { sign_id: s.id } });
      await api('/api/study/rate', { method: 'POST', body: { sign_id: s.id, known: isKnown } });
    } catch { toast('Відповідь не збережено.'); }
    window.setTimeout(() => void next(), 220);
  }

  async function next(): Promise<void> {
    tma.mainButton(null); tma.secondaryButton(null);
    let step: Step;
    try { step = await api<Step>('/api/study/next'); } catch (e) {
      if (e instanceof ApiErr && e.code === 'premium_required') { await refreshMe(); closeScreen(); return; }
      stage.replaceChildren(placeholder('Не вдалося завантажити', 'Перевірте з’єднання.')); return;
    }
    const s = 'sign_id' in step ? byId.get(step.sign_id) : undefined;
    if (step.mode === 'done' || !s) {
      stage.replaceChildren(placeholder('На зараз усе', step.mode === 'done' && step.next_in != null
        ? `Наступне повторення через ${duration(step.next_in)}.` : 'Усі знаки з добірки пройдено.'));
      tma.mainButton({ text: 'Готово', onClick: async () => { await refreshMe(); closeScreen(); } });
      return;
    }
    const isNew = step.mode === 'new';
    const back = h('div', { class: 'swipe-face is-back' },
      h('p', { class: 'tma-title3', style: 'margin:0' }, text(s.names)),
      transLang() ? h('p', { class: 'tma-hint', style: 'margin:0' }, text(s.names, transLang())) : '',
      h('p', { style: 'margin:0' }, text(s.descriptions)));
    const front = h('div', { class: 'swipe-face' }, art(s, true),
      h('p', { class: 'tma-footnote', style: 'margin:0' }, isNew ? 'Новий знак' : 'Що означає цей знак?'));
    const card = h('div', { class: 'swipe-card', role: 'button', tabindex: '0', 'aria-label': 'Картка знака, торкніться, щоб перевернути' }, front, back);
    stage.replaceChildren(card);
    let startX = 0, dx = 0, dragging = false;
    card.onpointerdown = (e) => { dragging = true; startX = e.clientX; dx = 0; card.setPointerCapture(e.pointerId); card.classList.add('is-dragging'); };
    card.onpointermove = (e) => {
      if (!dragging) return;
      dx = e.clientX - startX;
      card.style.transform = `translateX(${dx}px) rotate(${dx / 18}deg)`;
      card.dataset.lean = dx > 40 ? 'right' : dx < -40 ? 'left' : '';
    };
    card.onpointerup = () => {
      dragging = false; card.classList.remove('is-dragging');
      if (Math.abs(dx) > 90) { void rate(s, dx > 0, card, isNew); return; }
      card.style.transform = ''; card.dataset.lean = '';
      if (Math.abs(dx) < 6) { card.classList.toggle('is-flipped'); tma.haptic.tap(); }
    };
    tma.mainButton({ text: 'Знаю', onClick: () => void rate(s, true, card, isNew) });
    tma.secondaryButton({ text: 'Ще ні', onClick: () => void rate(s, false, card, isNew) });
  }
  draw();
  void next();
}

/* ---------------------------------------------------------------- tests */
function examRoot(): Kid[] {
  const blocked = gate();
  if (blocked) return [largeTitle('Тест'), ...blocked];
  const minutes = (n: number) => `${n} хв`;
  const seg = h('div', { class: 'tma-segmented', role: 'tablist', 'aria-label': 'Кількість питань' },
    ...EXAM_SIZES.map((n) => h('button', { type: 'button', role: 'tab', 'aria-selected': String(n === examSize),
      onclick: on(() => { if (n !== examSize) { examSize = n; tma.haptic.select(); renderRoot(); } }) }, `${n}`)));
  const need = Math.ceil(examSize * 38 / 45);
  tma.mainButton({ text: `Почати тест · ${examSize} питань`, onClick: () => startExam(examSize) });
  const recent = me.exams ?? [];
  return [largeTitle('Тест'),
    h('section', { class: 'tma-card' },
      h('p', { class: 'tma-hint', style: 'margin:0' }, 'Як на teoriprøven: знак і чотири варіанти, одна правильна відповідь. Результат і розбір — наприкінці.'),
      seg,
      h('dl', { class: 'tma-kv' },
        h('div', {}, h('dt', {}, 'Час'), h('dd', {}, minutes(examSize))),
        h('div', {}, h('dt', {}, 'Щоб скласти'), h('dd', {}, `${need} з ${examSize} правильно`)))),
    recent.length ? h('section', { class: 'tma-section', 'aria-labelledby': 'rec-h', style: 'margin-top:var(--tma-gap-section)' },
      h('h2', { class: 'tma-section__header', id: 'rec-h' }, 'Останні результати'),
      h('ul', { class: 'tma-list' }, ...recent.map((r) => h('li', {}, h('div', { class: 'tma-cell' },
        h('span', { class: 'tma-cell__body' }, h('span', { class: 'tma-cell__title' }, `${r.correct} з ${r.total}`),
          h('span', { class: 'tma-cell__subtitle' }, new Date(r.finished_at * 1000).toLocaleDateString('uk'))),
        h('span', { class: r.passed ? 'tma-cell__after exam-pass' : 'tma-cell__after' }, r.passed ? 'Складено' : 'Не складено')))))) : ''];
}

async function startExam(size: number): Promise<void> {
  let exam: Exam;
  try {
    exam = await api<Exam>('/api/exam/start', { method: 'POST', body: { size } });
  } catch (e) {
    if (e instanceof ApiErr && e.code === 'premium_required') { await refreshMe(); renderRoot(); return; }
    toast('Не вдалося почати тест. Спробуйте ще раз.');
    return;
  }
  const answers: (number | null)[] = exam.questions.map(() => null);
  const deadline = Date.now() + exam.seconds * 1000;
  let i = 0;
  let finished = false;
  const el = openScreen(() => void leave());
  tma.closingConfirmation(true);
  const counter = h('span', { class: 'tma-headline' });
  const clock = h('span', { class: 'tma-chip', 'aria-label': 'Залишилось часу' });
  const bar = h('i', {});
  const body = h('div', {});
  el.append(h('div', { class: 'exam-top' }, counter, clock), h('div', { class: 'tma-progress' }, bar), body);

  const tick = window.setInterval(() => {
    const left = Math.max(0, Math.round((deadline - Date.now()) / 1000));
    clock.textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`;
    if (left === 0) void finish();
  }, 500);

  async function leave(): Promise<void> {
    const ok = await tma.confirm('Завершити тест? Відповіді не збережуться.', async () => true  /* clients before 6.2: no native dialog, leave */);
    if (!ok) return;
    finished = true; clearInterval(tick); closeScreen();
  }
  function draw(): void {
    const q = exam.questions[i];
    counter.textContent = `Питання ${i + 1} з ${exam.questions.length}`;
    bar.style.width = `${(i / exam.questions.length) * 100}%`;
    const buttons = q.options.map((label, k) => h('button', { class: 'quiz-option', type: 'button',
      onclick: on(() => {
        if (finished) return;
        answers[i] = k;
        tma.haptic.select();
        for (const b of buttons) b.disabled = true;
        buttons[k].classList.add('is-picked');
        window.setTimeout(() => { if (i < exam.questions.length - 1) { i++; draw(); } else void finish(); }, 250);
      }) }, label) as HTMLButtonElement);
    body.replaceChildren(artBox(q.image, q.scale, `Знак, питання ${i + 1}`, true),
      h('div', { class: 'quiz-options', role: 'group', 'aria-label': 'Варіанти відповіді' }, ...buttons));
    tma.mainButton(i < exam.questions.length - 1
      ? { text: 'Пропустити', onClick: () => { i++; draw(); } }
      : { text: 'Завершити тест', onClick: () => void finish() });
    window.scrollTo(0, 0);
  }
  async function finish(): Promise<void> {
    if (finished) return;
    finished = true; clearInterval(tick);
    tma.mainButton({ text: 'Перевіряємо…', active: false, onClick: () => {} });
    try {
      const result = await api<ExamResult>('/api/exam/finish', { method: 'POST', body: { exam_id: exam.exam_id, answers } });
      tma.closingConfirmation(false);
      if (result.passed) tma.haptic.success(); else tma.haptic.warning();
      showResult(result, size);
    } catch {
      finished = false;
      tma.mainButton({ text: 'Надіслати ще раз', onClick: () => void finish() });
      toast('Результат не надіслано. Перевірте з’єднання.');
    }
  }
  draw();
}

function showResult(r: ExamResult, size: number): void {
  const el = openScreen(async () => { await refreshMe(); closeScreen(); });
  const mistakes = r.items.filter((x) => !x.ok);
  const need = Math.ceil(r.total * 38 / 45);
  el.append(
    h('div', { style: 'text-align:center;padding:var(--tma-s6) 0 var(--tma-s4)' },
      h('p', { class: 'tma-figure', style: 'margin:0' }, `${r.correct}`, h('span', { class: 'tma-figure__minor' }, ` з ${r.total}`)),
      h('span', { class: r.passed ? 'tma-chip is-success' : 'tma-chip' }, r.passed ? 'Складено' : 'Не складено'),
      h('p', { class: 'tma-hint', style: 'margin:var(--tma-s3) 0 0' },
        r.timed_out ? `Час вийшов. Щоб скласти, потрібно ${need} правильних.` : `Щоб скласти, потрібно ${need} правильних.`)),
    mistakes.length ? h('section', { class: 'tma-section', 'aria-labelledby': 'err-h' },
      h('h2', { class: 'tma-section__header', id: 'err-h' }, `Помилки · ${mistakes.length}`),
      h('ul', { class: 'tma-list' }, ...mistakes.map((m) => {
        const s = byId.get(m.sign_id);
        return h('li', {}, h('button', { class: 'tma-cell is-2', type: 'button', onclick: on(() => { if (s) openSign(s); }) },
          s ? h('span', { class: 'result-thumb' }, art(s)) : '',
          h('span', { class: 'tma-cell__body' },
            h('span', { class: 'tma-cell__title' }, m.correct),
            h('span', { class: 'tma-cell__subtitle' }, m.chosen ? `Ваша відповідь: ${m.chosen}` : 'Без відповіді'))));
      }))) : placeholder('Без жодної помилки', 'Можна братися за довший тест.'));
  tma.mainButton({ text: `Пройти ще раз · ${size} питань`, onClick: () => startExam(size) });
}

/* ---------------------------------------------------------------- progress */
function progressScreen(): Kid[] {
  const head = largeTitle('Прогрес');
  if (!tma.inTelegram || !me.registered) {
    return [head, placeholder(tma.inTelegram ? 'Ще немає прогресу' : 'Відкрийте з Telegram', tma.inTelegram
      ? 'Налаштуйте мови в боті й пройдіть кілька знаків — тут з’явиться ваш прогрес.'
      : 'Прогрес видно, коли застосунок відкрито кнопкою в боті.')];
  }
  const progress = me.progress ?? {};
  const masteredBox = me.mastered_box ?? 4;
  const total = signs.length;
  const mastered = signs.filter((s) => (progress[s.id]?.box ?? -1) >= masteredBox).length;
  const learning = signs.filter((s) => progress[s.id] && progress[s.id].box < masteredBox).length;
  const due = signs.filter((s) => progress[s.id]?.due).length;
  const pct = total ? Math.round((mastered / total) * 100) : 0;
  const accuracy = me.answered ? `${Math.round(((me.correct ?? 0) / me.answered) * 100)}% · ${me.correct}/${me.answered}` : '—';
  const st = me.premium;
  return [
    head,
    profileCard(),
    planSection(),
    h('section', { class: 'tma-card' },
      h('p', { class: 'tma-headline', style: 'margin:0' }, `Вивчено ${mastered} з ${total}`),
      h('div', { class: 'tma-progress', role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': String(total), 'aria-valuenow': String(mastered) },
        h('i', { style: `width:${pct}%` })),
      h('p', { class: 'tma-footnote', style: 'margin:0' }, `${pct}% бази знаків`)),
    h('dl', { class: 'tma-kv', style: 'margin-top:var(--tma-gap-section)' },
      h('div', {}, h('dt', {}, 'На вивченні'), h('dd', {}, String(learning))),
      h('div', {}, h('dt', {}, 'Час повторити'), h('dd', {}, String(due))),
      h('div', {}, h('dt', {}, 'Точність'), h('dd', {}, accuracy)),
      h('div', {}, h('dt', {}, 'Серія'), h('dd', {}, `${me.streak ?? 0} дн.`)),
      st?.paywall ? h('div', {}, h('dt', {}, 'Преміум'), h('dd', {}, st.active && st.expires_at
        ? `${st.renews ? 'продовження' : 'до'} ${new Date(st.expires_at * 1000).toLocaleDateString('uk')}` : 'ні')) : ''),
    h('section', { class: 'tma-section', 'aria-labelledby': 'cat-h', style: 'margin-top:var(--tma-gap-section)' },
      h('h2', { class: 'tma-section__header', id: 'cat-h' }, 'За категоріями'),
      h('ul', { class: 'tma-list' }, ...categories.map((c) => {
        const inCat = signs.filter((s) => s.category === c.code);
        const done = inCat.filter((s) => (progress[s.id]?.box ?? -1) >= masteredBox).length;
        return h('li', {}, h('button', { class: 'tma-cell', type: 'button',
          onclick: on(() => { category = c.code; tma.haptic.select(); setTab('signs'); }) },
          h('span', { class: 'tma-cell__body' }, h('span', { class: 'tma-cell__title' }, text(c.names, 'uk'))),
          h('span', { class: 'tma-cell__after' }, `${done}/${inCat.length}`)));
      }))),
  ];
}

/* ---------------------------------------------------------------- profile */
type TgUser = { first_name?: string; last_name?: string; username?: string; photo_url?: string; is_premium?: boolean };
const tgUser = (): TgUser => ((tma.tg as unknown as { initDataUnsafe?: { user?: TgUser } } | null)?.initDataUnsafe?.user ?? {});

function daysUntil(iso: string | null): number | null {
  if (!iso) return null;
  const ms = new Date(`${iso}T00:00:00`).getTime() - new Date(new Date().toDateString()).getTime();
  return Number.isFinite(ms) ? Math.round(ms / 86400000) : null;
}

function profileCard(): HTMLElement {
  const u = tgUser();
  const p = me.profile;
  const name = [u.first_name ?? p?.first_name, u.last_name].filter(Boolean).join(' ') || 'Учень';
  const initials = name.split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase();
  // photo_url comes from Telegram with the launch data; only shown, never stored
  const avatar = u.photo_url
    ? h('img', { class: 'profile-avatar', src: u.photo_url, alt: '', referrerpolicy: 'no-referrer' })
    : h('span', { class: 'profile-avatar is-initials', 'aria-hidden': 'true' }, initials);
  const days = daysUntil(p?.exam_date ?? null);
  const since = p?.member_since ? new Date(p.member_since * 1000).toLocaleDateString('uk', { month: 'long', year: 'numeric' }) : '';
  const chips: Kid[] = [h('span', { class: 'tma-chip' }, `Категорія ${p?.licence_class ?? 'B'}`)];
  if (days != null && days >= 0) chips.push(h('span', { class: 'tma-chip' }, days === 0 ? 'Іспит сьогодні' : `До іспиту ${days} ${plural(days, 'день', 'дні', 'днів')}`));
  if (me.premium?.paywall && me.premium.active) chips.push(h('span', { class: 'tma-chip is-success' }, 'Преміум'));
  return h('section', { class: 'tma-card profile-card' },
    h('div', { class: 'profile-head' }, avatar,
      h('div', {}, h('p', { class: 'tma-title3', style: 'margin:0' }, name),
        h('p', { class: 'tma-hint', style: 'margin:0' }, [u.username ? `@${u.username}` : '', since ? `з нами з ${since}` : ''].filter(Boolean).join(' · ')))),
    h('div', { style: 'display:flex;flex-wrap:wrap;gap:var(--tma-s2)' }, ...chips));
}

async function saveProfile(fields: Partial<Profile>): Promise<void> {
  try {
    await api('/api/profile', { method: 'POST', body: fields });
    me.profile = { ...(me.profile as Profile), ...fields };
    tma.haptic.select();
    theoryIndex = null;
    renderRoot();
  } catch {
    toast('Не вдалося зберегти. Спробуйте ще раз.');
  }
}

function planSection(): HTMLElement {
  const p = me.profile;
  const classes = theoryIndex?.classes ?? { B: { uk: 'Легковий (B)' }, AM146: { uk: 'Мопед (AM146)' }, A1: { uk: 'A1' }, A2: { uk: 'A2' }, A: { uk: 'A' } };
  const classChips = h('div', { class: 'tma-scroll-x', role: 'group', 'aria-label': 'Категорія прав' },
    ...Object.keys(classes).map((c) => h('button', { class: 'tma-chip', type: 'button', 'aria-pressed': String(p?.licence_class === c),
      onclick: on(() => { if (p?.licence_class !== c) void saveProfile({ licence_class: c }); }) }, c)));
  const date = h('input', { class: 'tma-input', type: 'date', value: p?.exam_date ?? '', 'aria-label': 'Дата іспиту' }) as HTMLInputElement;
  date.onchange = () => void saveProfile({ exam_date: date.value || null });
  const goals = h('div', { class: 'tma-segmented', role: 'tablist', 'aria-label': 'Денна мета' },
    ...[10, 20, 30, 50].map((g) => h('button', { type: 'button', role: 'tab', 'aria-selected': String(p?.daily_goal === g),
      onclick: on(() => { if (p?.daily_goal !== g) void saveProfile({ daily_goal: g }); }) }, `${g}`)));
  const remind = h('input', { type: 'checkbox', class: 'tma-switch', 'aria-label': 'Нагадування', ...(p?.reminders ? { checked: true } : {}) }) as HTMLInputElement;
  remind.onchange = () => void saveProfile({ reminders: remind.checked });
  const today = me.today ?? 0;
  const goal = p?.daily_goal ?? 10;
  return h('section', { class: 'tma-section', 'aria-labelledby': 'plan-h', style: 'margin-top:var(--tma-gap-section)' },
    h('h2', { class: 'tma-section__header', id: 'plan-h' }, 'Мій план'),
    h('div', { class: 'tma-card' },
      h('p', { class: 'tma-headline', style: 'margin:0' }, `Сьогодні ${Math.min(today, goal)} з ${goal} відповідей`),
      h('div', { class: 'tma-progress', role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': String(goal), 'aria-valuenow': String(Math.min(today, goal)) },
        h('i', { style: `width:${Math.min(100, Math.round((today / goal) * 100))}%` })),
      h('p', { class: 'tma-footnote', style: 'margin:var(--tma-s2) 0 0' }, 'Категорія прав'), classChips,
      h('p', { class: 'tma-footnote', style: 'margin:var(--tma-s2) 0 0' }, 'Дата іспиту'), date,
      h('p', { class: 'tma-footnote', style: 'margin:var(--tma-s2) 0 0' }, 'Денна мета, відповідей'), goals,
      h('label', { class: 'profile-toggle' }, h('span', {}, 'Нагадування в боті'), remind),
      p?.timezone ? h('p', { class: 'tma-footnote', style: 'margin:0' }, `Часовий пояс: ${p.timezone}`) : ''));
}

/* ---------------------------------------------------------------- start */
async function main(): Promise<void> {
  // open at full height straight away (the kit gates by client version inside the call)
  (tma.tg as unknown as { expand?: () => void } | null)?.expand?.();
  tma.chrome({ header: 'secondary_bg_color', background: 'secondary_bg_color', bottomBar: 'secondary_bg_color' });
  const start = parseStartParam(tma.launch.tgWebAppStartParam, {
    sign: /^sign-([0-9]{3}_[0-9A-Z]{1,4})$/, tab: /^(study|exam|progress)$/,
  });
  try {
    const [catalog, profile] = await Promise.all([
      api<{ categories: Category[]; signs: Sign[] }>('/api/catalog', { auth: false }),
      tma.inTelegram ? api<Me>('/api/me').catch(() => ({ registered: false })) : Promise.resolve({ registered: false }),
    ]);
    categories = catalog.categories; signs = catalog.signs; me = profile;
    byId = new Map(signs.map((s) => [s.id, s]));
  } catch {
    $('root').removeAttribute('aria-busy');
    $('root').replaceChildren(placeholder('Не вдалося завантажити знаки', 'Перевірте з’єднання й спробуйте ще раз.',
      h('button', { class: 'tma-btn is-tonal', type: 'button', onclick: on(() => location.reload()) }, 'Спробувати ще раз')));
    tma.ready();
    return;
  }
  // Time zone for reminders at a sane hour: taken from the device once, shown in the plan.
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  if (me.registered && me.profile && !me.profile.timezone && zone) void saveProfile({ timezone: zone });
  setTab(start?.route === 'tab' ? (start.match[1] as Tab) : 'signs');
  if (start?.route === 'sign') { const s = byId.get(start.match[1]); if (s) openSign(s); }
  tma.ready();
}
void main();
