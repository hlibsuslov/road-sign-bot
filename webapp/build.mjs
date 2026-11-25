// Builds webapp/dist from TypeScript with Node's own type stripping (Node >= 22.18). No packages.
//   node webapp/build.mjs           # build
//   node webapp/build.mjs --check   # exit 1 if dist is missing or older than its source
import { stripTypeScriptTypes } from 'node:module';
import { mkdirSync, readFileSync, statSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const FILES = { 'app.ts': 'app.js', '_kit/tma.ts': 'tma.js' };
const KIT_IMPORT = /from\s+['"]\.\/_kit\/([\w-]+)\.ts['"]/g;

process.removeAllListeners('warning'); // stripTypeScriptTypes is marked experimental
const check = process.argv.includes('--check');
let stale = 0;
for (const [src, out] of Object.entries(FILES)) {
  const from = join(here, src);
  const to = join(here, 'dist', out);
  if (check) {
    if (!existsSync(to) || statSync(to).mtimeMs < statSync(from).mtimeMs) { console.log(`stale: dist/${out}`); stale++; }
    continue;
  }
  const js = stripTypeScriptTypes(readFileSync(from, 'utf8'), { mode: 'strip' }).replace(KIT_IMPORT, "from './$1.js'");
  mkdirSync(dirname(to), { recursive: true });
  writeFileSync(to, `// Built by webapp/build.mjs from ${src}. Do not edit.\n${js}`);
  console.log(`built dist/${out}`);
}
if (check && stale) process.exit(1);
