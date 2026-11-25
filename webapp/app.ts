// Mini App base: the sign library and the learner's progress.
// Data: GET /api/catalog (public) and GET /api/me (Authorization: tma <initData>, checked on the server).
// Text goes through textContent only; nothing from data is parsed as markup.
import { createTma, parseStartParam } from './_kit/tma.ts';

type Lang = 'no' | 'en' | 'uk' | 'ru';
type Texts = Partial<Record<Lang, string>>;
type Category = { code: string; names: Texts; count: number };
type Sign = { id: string; number: string; category: string; shape: string | null; names: Texts; descriptions: Texts; extra: Texts };
type Progress = { box: number; due: boolean; correct: number; wrong: number };
type Me = {
  registered: boolean; study_language?: Lang; translation_language?: Lang | 'none';
  mastered_box?: number; max_box?: number; answered?: number; correct?: number; streak?: number;
  progress?: Record<string, Progress>;
};

const tma = createTma();
const $ = (id: string) => document.getElementById(id) as HTMLElement;
const ICONS = '_kit/icons.svg';

let categories: Category[] = [];
let signs: Sign[] = [];
let me: Me = { registered: false };
let tab: 'signs' | 'progress' = 'signs';
let category = 'all';
let query = '';

const studyLang = (): Lang => me.study_language ?? 'no';
const transLang = (): Lang | null => {
  const t = me.translation_language;
  return t && t !== 'none' && t !== studyLang() ? t : null;
};
const text = (t: Texts, lang: Lang | null = studyLang()) => (lang && t[lang]) || t.no || t.en || '';
const categoryName = (code: string) => text(categories.find((c) => c.code === code)?.names ?? {}, 'uk');

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
const art = (s: Sign, hero = false) => h('div', { class: hero ? 'sign-art is-hero' : 'sign-art' },
  h('img', { src: hero ? `signs/${s.id}.webp` : `signs/thumb/${s.id}.webp`, alt: hero ? `Знак ${s.number}: ${text(s.names)}` : '', loading: 'lazy', decoding: 'async' }));

function status(s: Sign): HTMLElement | null {
  const p = me.progress?.[s.id];
  if (!p) return null;
  const mastered = p.box >= (me.mastered_box ?? 4);
  const label = mastered ? 'Вивчено' : p.due ? 'Час повторити' : `Рівень ${p.box}`;
  return h('span', { class: mastered ? 'sign-status is-mastered' : 'sign-status' }, label);
}

/* ---------------------------------------------------------------- API */
async function getJson<T>(path: string, auth = false): Promise<T> {
  const headers: Record<string, string> = {};
  if (auth) headers.Authorization = `tma ${tma.tg?.initData ?? ''}`;
  const res = await fetch(path, { headers });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

/* ---------------------------------------------------------------- navigation */
function setTab(t: typeof tab): void {
  tab = t;
  for (const b of document.querySelectorAll<HTMLButtonElement>('[data-tab]')) b.setAttribute('aria-selected', String(b.dataset.tab === t));
  renderRoot();
  window.scrollTo(0, 0);
}
for (const b of document.querySelectorAll<HTMLButtonElement>('[data-tab]')) {
  b.onclick = () => { if (b.dataset.tab !== tab) { tma.haptic.select(); setTab(b.dataset.tab as typeof tab); } };
}
function openDetail(s: Sign): void {
  const el = $('detail');
  el.replaceChildren(...signDetail(s));
  $('root').hidden = true; el.hidden = false; $('tabbar').hidden = true;
  if (tma.nav.top?.id !== 'detail') tma.nav.push({ id: 'detail', kind: 'screen', onBack: closeDetail });
  window.scrollTo(0, 0);
}
function closeDetail(): void {
  tma.nav.pop('detail');
  $('detail').hidden = true; $('root').hidden = false; $('tabbar').hidden = false;
  $('root').classList.add('is-back');
}

/* ---------------------------------------------------------------- library */
function renderRoot(): void {
  const root = $('root');
  root.removeAttribute('aria-busy');
  if (tab === 'progress') { root.replaceChildren(...progressScreen()); return; }
  const search = h('input', { type: 'search', placeholder: 'Назва або номер', 'aria-label': 'Пошук знака', value: query }) as HTMLInputElement;
  search.oninput = () => { query = search.value.trim().toLowerCase(); renderList(); };
  const chips = h('div', { class: 'tma-scroll-x', role: 'group', 'aria-label': 'Категорія', style: 'margin-top:var(--tma-s3)' },
    ...[{ code: 'all', label: 'Усі' }, ...categories.map((c) => ({ code: c.code, label: text(c.names, 'uk') }))].map((c) =>
      h('button', { class: 'tma-chip', type: 'button', 'aria-pressed': String(category === c.code),
        onclick: (() => { if (category !== c.code) { category = c.code; tma.haptic.select(); renderRoot(); } }) as EventListener }, c.label)));
  root.replaceChildren(
    h('header', { class: 'tma-header' }, h('h1', { class: 'tma-large-title' }, 'Дорожні знаки')),
    h('label', { class: 'tma-search' }, icon('search'), search),
    chips,
    h('div', { id: 'list', style: 'margin-top:var(--tma-gap-section)' }));
  renderList();
}

function matches(s: Sign): boolean {
  if (category !== 'all' && s.category !== category) return false;
  if (!query) return true;
  return s.number.startsWith(query) ||
    Object.values(s.names).some((n) => (n ?? '').toLowerCase().includes(query));
}

function renderList(): void {
  const list = $('list');
  const items = signs.filter(matches);
  if (!items.length) {
    list.replaceChildren(h('div', { class: 'tma-placeholder' },
      h('p', { class: 'tma-placeholder__title' }, 'Нічого не знайдено'),
      h('p', { class: 'tma-placeholder__text' }, 'Спробуйте інше слово або номер знака.'),
      h('button', { class: 'tma-btn is-tonal', type: 'button', onclick: (() => { query = ''; category = 'all'; renderRoot(); }) as EventListener }, 'Скинути пошук')));
    return;
  }
  list.replaceChildren(
    h('p', { class: 'tma-footnote', style: 'margin:0 0 var(--tma-s3)', 'aria-live': 'polite' }, `Знаків: ${items.length}`),
    h('div', { class: 'sign-grid' }, ...items.map((s) =>
      h('a', { class: 'sign-tile', href: `#sign-${s.id}`, onclick: ((e: Event) => { e.preventDefault(); tma.haptic.tap(); openDetail(s); }) as EventListener },
        art(s),
        h('span', { class: 'tma-meta' }, s.number),
        h('span', { class: 'sign-tile__name' }, text(s.names)),
        status(s)))));
}

/* ---------------------------------------------------------------- sign detail */
function signDetail(s: Sign): Kid[] {
  const trans = transLang();
  const extra = text(s.extra);
  const about = h('p', { class: 'tma-clamp-3', style: 'margin:0' }, extra);
  const p = me.progress?.[s.id];
  const similar = signs.filter((x) => x.category === s.category && x.id !== s.id).slice(0, 8);
  return [
    art(s, true),
    h('h1', { class: 'tma-title2', style: 'text-align:center' }, text(s.names)),
    trans ? h('p', { class: 'tma-subhead tma-hint', style: 'text-align:center;margin:var(--tma-s1) 0 0' }, text(s.names, trans)) : null,
    h('div', { class: 'tma-stack', style: 'margin-top:var(--tma-gap-section)' },
      h('section', { class: 'tma-card' },
        h('p', { style: 'margin:0' }, text(s.descriptions)),
        trans ? h('p', { class: 'tma-hint', style: 'margin:0' }, text(s.descriptions, trans)) : null),
      extra ? h('section', { class: 'tma-card', 'aria-labelledby': 'about-h' },
        h('h2', { class: 'tma-headline', id: 'about-h', style: 'margin:0' }, 'Пояснення'), about,
        h('button', { class: 'tma-btn is-plain', type: 'button', onclick: ((e: Event) => { about.classList.remove('tma-clamp-3'); (e.currentTarget as HTMLElement).remove(); }) as EventListener }, 'Читати повністю')) : null,
      h('dl', { class: 'tma-kv' },
        h('div', {}, h('dt', {}, 'Номер'), h('dd', {}, s.number)),
        h('div', {}, h('dt', {}, 'Категорія'), h('dd', {}, categoryName(s.category))),
        p ? h('div', {}, h('dt', {}, 'Відповіді'), h('dd', {}, `${p.correct} правильно · ${p.wrong} помилок`)) : null),
      similar.length ? h('section', { class: 'tma-section', 'aria-labelledby': 'sim-h' },
        h('h2', { class: 'tma-section__header', id: 'sim-h' }, 'Ще в цій категорії'),
        h('div', { class: 'tma-carousel', style: '--x:0' }, ...similar.map((x) =>
          h('a', { class: 'sign-tile', href: `#sign-${x.id}`, style: 'flex:0 0 30%',
            onclick: ((e: Event) => { e.preventDefault(); tma.haptic.tap(); openDetail(x); }) as EventListener },
            art(x), h('span', { class: 'sign-tile__name' }, text(x.names)))))) : null),
  ];
}

/* ---------------------------------------------------------------- progress */
function progressScreen(): Kid[] {
  const head = h('header', { class: 'tma-header' }, h('h1', { class: 'tma-large-title' }, 'Прогрес'));
  if (!tma.inTelegram || !me.registered) {
    return [head, h('div', { class: 'tma-placeholder' },
      h('p', { class: 'tma-placeholder__title' }, tma.inTelegram ? 'Ще немає прогресу' : 'Відкрийте з Telegram'),
      h('p', { class: 'tma-placeholder__text' }, tma.inTelegram
        ? 'Налаштуйте мови в боті й пройдіть кілька знаків — тут з’явиться ваш прогрес.'
        : 'Прогрес видно, коли застосунок відкрито кнопкою в боті.'))];
  }
  const progress = me.progress ?? {};
  const masteredBox = me.mastered_box ?? 4;
  const total = signs.length;
  const mastered = signs.filter((s) => (progress[s.id]?.box ?? -1) >= masteredBox).length;
  const learning = signs.filter((s) => progress[s.id] && progress[s.id].box < masteredBox).length;
  const due = signs.filter((s) => progress[s.id]?.due).length;
  const pct = total ? Math.round((mastered / total) * 100) : 0;
  const accuracy = me.answered ? `${Math.round(((me.correct ?? 0) / me.answered) * 100)}% · ${me.correct}/${me.answered}` : '—';
  return [
    head,
    h('section', { class: 'tma-card' },
      h('p', { class: 'tma-headline', style: 'margin:0' }, `Вивчено ${mastered} з ${total}`),
      h('div', { class: 'progress-bar', role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': String(total), 'aria-valuenow': String(mastered) },
        h('span', { style: `width:${pct}%` })),
      h('p', { class: 'tma-footnote', style: 'margin:0' }, `${pct}% бази знаків`)),
    h('dl', { class: 'tma-kv', style: 'margin-top:var(--tma-gap-section)' },
      h('div', {}, h('dt', {}, 'На вивченні'), h('dd', {}, String(learning))),
      h('div', {}, h('dt', {}, 'Час повторити'), h('dd', {}, String(due))),
      h('div', {}, h('dt', {}, 'Точність'), h('dd', {}, accuracy)),
      h('div', {}, h('dt', {}, 'Серія'), h('dd', {}, `${me.streak ?? 0} дн.`))),
    h('section', { class: 'tma-section', 'aria-labelledby': 'cat-h', style: 'margin-top:var(--tma-gap-section)' },
      h('h2', { class: 'tma-section__header', id: 'cat-h' }, 'За категоріями'),
      h('ul', { class: 'tma-list' }, ...categories.map((c) => {
        const inCat = signs.filter((s) => s.category === c.code);
        const done = inCat.filter((s) => (progress[s.id]?.box ?? -1) >= masteredBox).length;
        return h('li', {}, h('button', { class: 'tma-cell', type: 'button',
          onclick: (() => { category = c.code; tma.haptic.select(); setTab('signs'); }) as EventListener },
          h('span', { class: 'tma-cell__body' }, h('span', { class: 'tma-cell__title' }, text(c.names, 'uk'))),
          h('span', { class: 'tma-cell__after' }, `${done}/${inCat.length}`)));
      }))),
  ];
}

/* ---------------------------------------------------------------- start */
function failed(): void {
  $('root').removeAttribute('aria-busy');
  $('root').replaceChildren(h('div', { class: 'tma-placeholder' },
    h('p', { class: 'tma-placeholder__title' }, 'Не вдалося завантажити знаки'),
    h('p', { class: 'tma-placeholder__text' }, 'Перевірте з’єднання й спробуйте ще раз.'),
    h('button', { class: 'tma-btn is-tonal', type: 'button', onclick: (() => location.reload()) as EventListener }, 'Спробувати ще раз')));
}

async function main(): Promise<void> {
  tma.chrome({ header: 'secondary_bg_color', background: 'secondary_bg_color', bottomBar: 'secondary_bg_color' });
  const start = parseStartParam(tma.launch.tgWebAppStartParam, { sign: /^sign-([0-9]{3}_[0-9A-Z]{1,4})$/, progress: /^progress$/ });
  try {
    const [catalog, profile] = await Promise.all([
      getJson<{ categories: Category[]; signs: Sign[] }>('/api/catalog'),
      tma.inTelegram ? getJson<Me>('/api/me', true).catch(() => ({ registered: false })) : Promise.resolve({ registered: false }),
    ]);
    categories = catalog.categories; signs = catalog.signs; me = profile;
  } catch {
    failed(); tma.ready(); return;
  }
  setTab(start?.route === 'progress' ? 'progress' : 'signs');
  if (start?.route === 'sign') { const s = signs.find((x) => x.id === start.match[1]); if (s) openDetail(s); }
  tma.ready();
}
void main();
