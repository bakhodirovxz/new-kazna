// Prototipdagi `const GEO={...};` qatoridan xarita geometriyasini JSON sifatida ajratadi.
// Foydalanish: node frontend/scripts/extract-geo.mjs <prototype.js> <chiqish.json>
import { readFileSync, writeFileSync } from 'node:fs';

const [source, target] = process.argv.slice(2);
if (!source || !target) throw new Error('usage: extract-geo.mjs <prototype.js> <out.json>');
const line = readFileSync(source, 'utf8').split('\n').find((l) => l.startsWith('const GEO='));
if (!line) throw new Error('GEO topilmadi');
const geo = JSON.parse(line.slice('const GEO='.length).trim().replace(/;$/, ''));
for (const key of ['W', 'H', 'reg', 'ins', 'inset', 'main', 'insp']) {
  if (!(key in geo)) throw new Error(`GEO.${key} yo'q`);
}
if (geo.reg.length !== geo.ins.length) throw new Error('reg va ins uzunligi mos emas');
const out = {
  W: geo.W, H: geo.H, inset: geo.inset, main: geo.main, insp: geo.insp,
  reg: geo.reg.map((r) => ({ n: r.n, d: r.d, ...(r.x === undefined ? {} : { x: r.x, y: r.y }), ...(r.city ? { city: true } : {}) })),
  ins: geo.ins,
};
writeFileSync(target, JSON.stringify(out));
console.log(`regions=${out.reg.length} bytes=${JSON.stringify(out).length}`);
