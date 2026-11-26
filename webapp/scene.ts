// Traffic situations drawn from data (data/theory/questions.json → image.scene).
// Norway drives on the right. One 300×300 view box; four templates:
//   crossroad   four arms N, E, S, W          t_junction  arms E, S, W
//   roundabout  ring with four arms            road        one straight two-lane road
// Spec: { scene, you: {from, to, parked?, broken?}, actors: [{kind:'car', from, to, inside?}],
//         signs: [{id, arm}], crossing?, pedestrians: [{side:'E'|'W', walking?}], triangle? }
// Colours come from CSS variables (app.css) so the scene follows the Telegram theme.

export type Arm = 'N' | 'E' | 'S' | 'W';
export type SceneSpec = {
  scene: 'crossroad' | 't_junction' | 'roundabout' | 'road';
  you?: { from: Arm; to?: Arm; parked?: boolean; broken?: boolean };
  actors?: { kind: 'car'; from: Arm; to?: Arm; inside?: boolean }[];
  signs?: { id: string; arm: Arm }[];
  crossing?: boolean;
  pedestrians?: { side: 'E' | 'W'; walking?: boolean }[];
  triangle?: boolean;
};

const NS = 'http://www.w3.org/2000/svg';
const C = 150;            // centre
const ROAD = 90;          // road width (two lanes)
const LANE = 22;          // lane centre offset from the middle line
const ROT: Record<Arm, number> = { S: 0, N: 180, E: 270, W: 90 };   // heading away from the arm

function el(tag: string, attrs: Record<string, string | number>, ...kids: SVGElement[]): SVGElement {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  for (const kid of kids) node.append(kid);
  return node;
}

/** Car centre for a vehicle approaching the junction from an arm, in its right-hand lane. */
function approach(arm: Arm, dist: number): [number, number] {
  switch (arm) {
    case 'S': return [C + LANE, C + ROAD / 2 + dist];
    case 'N': return [C - LANE, C - ROAD / 2 - dist];
    case 'E': return [C + ROAD / 2 + dist, C - LANE];
    case 'W': return [C - ROAD / 2 - dist, C + LANE];
  }
}
/** Where a vehicle leaves the picture through an arm (outgoing right-hand lane). */
function exit(arm: Arm): [number, number] {
  switch (arm) {
    case 'N': return [C + LANE, 12];
    case 'S': return [C - LANE, 288];
    case 'E': return [288, C + LANE];
    case 'W': return [12, C - LANE];
  }
}

function car(x: number, y: number, rot: number, role: 'you' | 'other' | 'broken', label?: string): SVGElement {
  const fill = role === 'you' ? 'var(--scene-you)' : role === 'broken' ? 'var(--scene-you)' : 'var(--scene-car)';
  const g = el('g', { transform: `translate(${x} ${y}) rotate(${rot})` },
    el('rect', { x: -11, y: -19, width: 22, height: 38, rx: 6, fill, stroke: 'var(--scene-outline)', 'stroke-width': 1.5 }),
    el('rect', { x: -8, y: -12, width: 16, height: 8, rx: 2, fill: 'var(--scene-glass)' }),
    el('rect', { x: -8, y: 8, width: 16, height: 6, rx: 2, fill: 'var(--scene-glass)' }));
  if (role === 'broken') {
    g.append(el('circle', { cx: -9, cy: -17, r: 3, fill: 'var(--scene-hazard)' }), el('circle', { cx: 9, cy: -17, r: 3, fill: 'var(--scene-hazard)' }),
      el('circle', { cx: -9, cy: 17, r: 3, fill: 'var(--scene-hazard)' }), el('circle', { cx: 9, cy: 17, r: 3, fill: 'var(--scene-hazard)' }));
  }
  if (label) {
    const t = el('text', { x: 0, y: 34, 'text-anchor': 'middle', 'font-size': 11, 'font-weight': 600, fill: 'var(--scene-label)', transform: `rotate(${-rot})` });
    t.textContent = label;
    g.append(t);
  }
  return g;
}

function arrow(from: [number, number], to: [number, number], via: [number, number], you: boolean): SVGElement {
  return el('path', {
    d: `M ${from[0]} ${from[1]} Q ${via[0]} ${via[1]} ${to[0]} ${to[1]}`, fill: 'none',
    stroke: you ? 'var(--scene-you)' : 'var(--scene-car)', 'stroke-width': 4, 'stroke-linecap': 'round',
    'stroke-dasharray': '2 8', 'marker-end': you ? 'url(#arrow-you)' : 'url(#arrow-car)', opacity: 0.9,
  });
}

function route(from: Arm, to: Arm, you: boolean): SVGElement {
  const [x, y] = approach(from, 30);
  const start: [number, number] = from === 'S' ? [x, y - 22] : from === 'N' ? [x, y + 22] : from === 'E' ? [x - 22, y] : [x + 22, y];
  const end = exit(to);
  const vertical = from === 'N' || from === 'S';
  const via: [number, number] = vertical ? [start[0], end[1]] : [end[0], start[1]];
  return arrow(start, end, via, you);
}

function signAt(id: string, arm: Arm): SVGElement {
  const pos: Record<Arm, [number, number]> = {
    S: [C + ROAD / 2 + 8, C + ROAD / 2 + 52], N: [C - ROAD / 2 - 38, C - ROAD / 2 - 82],
    E: [C + ROAD / 2 + 52, C - ROAD / 2 - 38], W: [C - ROAD / 2 - 82, C + ROAD / 2 + 8],
  };
  const [x, y] = pos[arm];
  return el('g', {},
    el('rect', { x: x + 13, y: y + 26, width: 4, height: 18, fill: 'var(--scene-outline)' }),
    el('image', { href: `signs/thumb/${id}.webp`, x, y, width: 30, height: 30 }));
}

function markers(): SVGElement {
  const head = (id: string, color: string) => el('marker', { id, viewBox: '0 0 10 10', refX: 5, refY: 5, markerWidth: 4, markerHeight: 4, orient: 'auto-start-reverse' },
    el('path', { d: 'M 0 0 L 10 5 L 0 10 z', fill: color }));
  return el('defs', {}, head('arrow-you', 'var(--scene-you)'), head('arrow-car', 'var(--scene-car)'));
}

function dashes(x1: number, y1: number, x2: number, y2: number): SVGElement {
  return el('line', { x1, y1, x2, y2, stroke: 'var(--scene-line)', 'stroke-width': 3, 'stroke-dasharray': '14 12' });
}

function junction(arms: Arm[]): SVGElement[] {
  const half = ROAD / 2;
  const out: SVGElement[] = [];
  if (arms.includes('N') || arms.includes('S')) {
    const top = arms.includes('N') ? 0 : C - half;
    const bottom = arms.includes('S') ? 300 : C + half;
    out.push(el('rect', { x: C - half, y: top, width: ROAD, height: bottom - top, fill: 'var(--scene-road)' }));
  }
  out.push(el('rect', { x: arms.includes('W') ? 0 : C - half, y: C - half, width: (arms.includes('E') ? 300 : C + half) - (arms.includes('W') ? 0 : C - half), height: ROAD, fill: 'var(--scene-road)' }));
  if (arms.includes('N')) out.push(dashes(C, 0, C, C - half - 6));
  if (arms.includes('S')) out.push(dashes(C, C + half + 6, C, 300));
  if (arms.includes('W')) out.push(dashes(0, C, C - half - 6, C));
  if (arms.includes('E')) out.push(dashes(C + half + 6, C, 300, C));
  return out;
}

function roundabout(): SVGElement[] {
  return [
    ...junction(['N', 'E', 'S', 'W']),
    el('circle', { cx: C, cy: C, r: 100, fill: 'var(--scene-road)' }),
    el('circle', { cx: C, cy: C, r: 44, fill: 'var(--scene-grass)', stroke: 'var(--scene-line)', 'stroke-width': 3 }),
  ];
}

function straightRoad(spec: SceneSpec): SVGElement[] {
  const out = [el('rect', { x: C - ROAD / 2, y: 0, width: ROAD, height: 300, fill: 'var(--scene-road)' }), dashes(C, 0, C, 300)];
  if (spec.crossing) {
    for (let x = C - ROAD / 2 + 4; x < C + ROAD / 2 - 4; x += 14) {
      out.push(el('rect', { x, y: 96, width: 8, height: 34, fill: 'var(--scene-zebra)' }));
    }
  }
  for (const p of spec.pedestrians ?? []) {
    const x = p.side === 'E' ? C + ROAD / 2 + 14 : C - ROAD / 2 - 14;
    out.push(el('g', { transform: `translate(${x} 113)` },
      el('circle', { cx: 0, cy: -9, r: 5, fill: 'var(--scene-person)' }),
      el('rect', { x: -5, y: -3, width: 10, height: 16, rx: 4, fill: 'var(--scene-person)' })));
    if (p.walking) {
      const dir = p.side === 'E' ? -1 : 1;
      out.push(arrow([x + dir * 10, 113], [x + dir * 52, 113], [x + dir * 30, 113], false));
    }
  }
  return out;
}

export function renderScene(spec: SceneSpec, label: string): SVGSVGElement {
  const svg = document.createElementNS(NS, 'svg') as SVGSVGElement;
  svg.setAttribute('viewBox', '0 0 300 300');
  svg.setAttribute('class', 'scene');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', label);
  svg.append(markers(), el('rect', { x: 0, y: 0, width: 300, height: 300, fill: 'var(--scene-grass)' }));

  if (spec.scene === 'road') {
    svg.append(...straightRoad(spec));
    if (spec.you) {
      const y = spec.you.parked ? 190 : spec.you.broken ? 150 : 225;
      svg.append(car(C + LANE + (spec.you.parked ? 8 : 0), y, 0, spec.you.broken ? 'broken' : 'you', 'Ви'));
      if (spec.you.parked && spec.crossing) {
        svg.append(el('line', { x1: 205, y1: 132, x2: 205, y2: 170, stroke: 'var(--scene-label)', 'stroke-width': 1.5, 'marker-end': 'url(#arrow-car)', 'marker-start': 'url(#arrow-car)' }));
        const t = el('text', { x: 212, y: 156, 'font-size': 13, 'font-weight': 700, fill: 'var(--scene-label)' });
        t.textContent = '? м';
        svg.append(t);
      }
      if (spec.triangle) {
        svg.append(el('path', { d: `M ${C + LANE} 262 l 11 19 h -22 z`, fill: 'none', stroke: 'var(--scene-hazard)', 'stroke-width': 4, 'stroke-linejoin': 'round' }));
      }
    }
    return svg;
  }

  svg.append(...(spec.scene === 'roundabout' ? roundabout() : junction(spec.scene === 't_junction' ? ['E', 'S', 'W'] : ['N', 'E', 'S', 'W'])));
  for (const s of spec.signs ?? []) svg.append(signAt(s.id, s.arm));
  const ring = 72;
  for (const a of spec.actors ?? []) {
    if (a.inside && spec.scene === 'roundabout') {
      const angle = { E: 0, S: 90, W: 180, N: 270 }[a.from] * Math.PI / 180;
      const heading = { E: 0, S: 90, W: 180, N: 270 }[a.from];   // counter-clockwise on screen
      svg.append(car(C + ring * Math.cos(angle), C + ring * Math.sin(angle), heading, 'other'));
      continue;
    }
    if (a.to && spec.scene !== 'roundabout') svg.append(route(a.from, a.to, false));
    svg.append(car(...approach(a.from, 30), ROT[a.from], 'other'));
  }
  if (spec.you) {
    const dist = spec.scene === 'roundabout' ? 62 : 30;
    if (spec.you.to && spec.scene !== 'roundabout') svg.append(route(spec.you.from, spec.you.to, true));
    svg.append(car(...approach(spec.you.from, dist), ROT[spec.you.from], 'you', 'Ви'));
  }
  return svg;
}
