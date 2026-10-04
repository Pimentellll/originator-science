/**
 * Browser smoke against the REAL stack (Vite dev server -> /api proxy -> H0 harness). Maps to the ten demo
 * requirements. Needs `playwright-core` (not a project dependency) and a Chromium:
 *
 *   MIRAGE_API_PROXY=http://localhost:8100 MIRAGE_EVAL_TOKEN=<same-local-value> VITE_MIRAGE_EVALUATION=1 npx vite &
 *   node dev/smoke.mjs <screenshot-dir> [http://localhost:5173/]
 */
import { chromium } from 'playwright-core'
import fs from 'fs'
const out = process.argv[2]
const base = process.argv[3] || 'http://localhost:5173/'
const exe = fs.readdirSync(process.env.HOME + '/.cache/ms-playwright').filter(d => d.startsWith('chromium-'))[0]
const path = `${process.env.HOME}/.cache/ms-playwright/${exe}/chrome-linux64/chrome`
const browser = await chromium.launch({ executablePath: fs.existsSync(path) ? path : undefined })
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } })
const logs = [], api = []
page.on('console', m => { if (['error', 'warning'].includes(m.type())) logs.push(`${m.type()}: ${m.text()}`) })
page.on('pageerror', e => logs.push('pageerror: ' + e.message))
page.on('response', r => { const u = r.url(); if (u.includes('/api/')) api.push(`${r.request().method()} ${u.replace(/^https?:\/\/[^/]+/, '').replace(/ep-[a-z0-9]+/g, 'ep-*')} ${r.status()}`) })
let failures = 0
const ok = (cond, msg) => { console.log(`${cond ? 'PASS' : 'FAIL'}  ${msg}`); if (!cond) failures++ }
const shot = async (name, wait = 600) => { await page.waitForTimeout(wait); await page.screenshot({ path: `${out}/${name}.png` }) }
const txt = (sel) => page.textContent(sel).then(t => t.replace(/\s+/g, ' '))
const run = async () => { await page.click('.act__ctl .btn--primary'); await page.waitForTimeout(1000) }

// 1. reset a RECEPTOR_BINDER_RESCUE campaign
await page.goto(base); await page.waitForSelector('.cockpit', { timeout: 20000 })
await page.fill('input[aria-label="Campaign seed"]', '9'); await page.click('text=RESET CAMPAIGN'); await page.waitForTimeout(1200)
const hdr = await txt('.hdr')
ok(/RECEPTOR_BINDER_RESCUE/.test(hdr), '1  reset campaign: RECEPTOR_BINDER_RESCUE profile shown')
ok(/LIVE/.test(hdr) && !/DEV \/ MOCK/.test(hdr), '1  header is LIVE, no MOCK pill')
ok(/Causal rescue planning/.test(hdr) && /EGFR-inspired receptor-binding campaign/.test(hdr) && /semi-mechanistic synthetic benchmark/i.test(hdr), '   positioning language visible')
// 2. public candidate / resources / belief
ok(/binder-000/.test(await txt('.cand')), '2  candidate binder-000 shown')
ok((await page.locator('.brow').count()) === 8, '2  eight causal-belief rows')
ok(/MOLECULE/.test(await txt('.belief')) && /EXPERIMENT/.test(await txt('.belief')) && /BIOLOGICAL MODEL/.test(await txt('.belief')), '   failure localisation: three explicit groups')
ok(/12\.0/.test(await txt('.res')), '2  resources (budget total 12.0) shown')
await shot('e1-01-reset-initial')
// 3. policy recommendation
const act0 = await txt('.act')
ok(/Size-exclusion/.test(act0) && /SEC/.test(act0), '3  recommendation requested: rescue planner proposes SEC first')
ok(/recommended action only/.test(act0), '   panel honestly says the API supplies the action only')
const H0 = await page.textContent('.belief__list')
// 4-6. execute experiment, structured measurements, belief update
await run()
const cand1 = await txt('.cand')
ok(/monomer fraction\s*[\d.]+/.test(cand1), '4/5  SEC executed; structured measurement (monomer fraction) shown')
ok((await page.textContent('.belief__list')) !== H0, '6  belief updated after the observation')
const deltas = await page.locator('.brow__d.is-up, .brow__d.is-down').count()
ok(deltas > 0, '6  belief deltas highlighted')
await shot('e1-02-after-sec')
// 7-8. redesign + lineage
ok(/Redesign for solubility/.test(await txt('.act')), '7  next recommended: solubility redesign')
await run()
const cand2 = await txt('.cand')
ok(/GEN 1/.test(cand2) && /parent binder-000/.test(cand2), '8  lineage: GEN 1 child of binder-000')
ok((await page.locator('.lineage__gen').count()) >= 2, '8  lineage trail has two nodes')
await shot('e1-03-after-redesign')
await run() // SPR on the redesigned candidate
const cand3 = await txt('.cand')
ok(/log KD/.test(cand3) && /log koff/.test(cand3), '5  SPR: multi-measurement observation (log KD + log koff)')
ok(/1\.00/.test(await txt('.res')), '   SPR instrument health preserved at 1.00')
await shot('e1-04-after-spr')
// justification panel
const just = await txt('.just')
ok(/Leading explanation/.test(just) && /Evidence still required/.test(just), '   justification panel renders public-data rows')
ok(/NOT AVAILABLE/.test(just), '   threshold verdict honestly NOT AVAILABLE (no certificate)')
// finish
for (let i = 0; i < 6; i++) { if (/Episode complete/.test(await txt('.act'))) break; await run() }
// 10. final correct-vs-justified
const fin = await txt('.act')
ok(/Episode complete/.test(fin), '10 episode reached its terminal decision')
ok(/CORRECT/.test(fin) && /JUSTIFIED/.test(fin) && !/NOT JUSTIFIED/.test(fin), '10 final evaluation: CORRECT + JUSTIFIED shown')
ok(/Justification checks/.test(fin), '10 justification checks listed')
await shot('e1-05-terminal-verdict', 900)
// 9. scrub replay
const stepBefore = await txt('.hdr__stats')
await page.click('button[aria-label="Previous step"]'); await page.waitForTimeout(500)
ok((await txt('.hdr__stats')) !== stepBefore, '9  scrubbing back changes the step')
await page.click('button[aria-label="First step"]'); await page.waitForTimeout(500)
ok(/Size-exclusion/.test(await txt('.act')) && /GEN 0/.test(await txt('.cand')), '9  scrub to step 0 restores the initial recommendation and candidate')
await page.click('text=WHY?'); await shot('e1-06-why'); await page.keyboard.press('Escape')
// greedy EIG on the same seed
console.log('selects:', await page.locator('.hdr select').evaluateAll(els => els.map(e => e.getAttribute('aria-label') + ':' + e.value))); console.log('hdr:', (await txt('.hdr')).slice(0, 200))
await page.selectOption('select[aria-label="Policy"]', { label: 'GREEDY EIG' }); await page.waitForTimeout(1200)
ok(/Surface plasmon/.test(await txt('.act')), '   greedy EIG recommends SPR first')
await run()
const g = await txt('.res')
ok(/0\.72/.test(g) && /Damaged|Degraded/.test(g), '   greedy EIG: premature SPR degrades the instrument (0.72)')
ok(/degraded/i.test(await txt('.cand')), '   observation quality flagged degraded')
await shot('e1-07-greedy-spr-damage')
// 10b. greedy -> lucky-correct
for (let i = 0; i < 14; i++) { if (/Episode complete/.test(await txt('.act'))) break; await run() }
const gfin = await txt('.act')
ok(/LUCKY-CORRECT/.test(gfin) && /NOT JUSTIFIED/.test(gfin), '10 greedy EIG verdict: lucky-correct, NOT JUSTIFIED')
await shot('e1-08-greedy-lucky-correct', 900)
// compare
await page.evaluate(() => { location.hash = '/compare' })
try { await page.waitForSelector('.cmp', { timeout: 30000 }) } catch (e) { console.log('COMPARE STUCK; page says:', (await txt('.app__main')).slice(0, 300)); console.log(api.slice(-12).join('\n')); throw e }
await page.waitForTimeout(500)
await page.click('text=SHOW ALL'); await shot('e1-09-compare', 1500)
const cmp = await txt('.cmp')
ok((await page.locator('.lane:not(.lane--notrun)').count()) === 4, 'C  four real lanes (rescue planner, greedy, fixed, random)')
for (const n of ['LOOKAHEAD', 'PPO']) { const t = await txt(`section[aria-label^="${n}"]`); ok(/NOT RUN/.test(t) && !/LIVE TRACE|MOCK/.test(t), `C  ${n} is a plain NOT RUN row`) }
ok(!/DEV \/ MOCK/.test(cmp), 'C  no mock content in live compare')
ok(/better scientific campaign/.test(cmp), 'C  thesis shown because the data back it (planner keeps SPR healthier)')
ok(/LUCKY|NOT JUSTIFIED|JUSTIFIED/.test(cmp), 'C  lane verdicts present')
// lab
await page.evaluate(() => { location.hash = '/benchmark' }); await page.waitForSelector('.lab'); await shot('e1-10-lab')
ok(/NOT RUN/.test(await txt('.lab')) && !/DEV \/ MOCK DATA/.test(await txt('.lab')), 'L  benchmark lab: NOT RUN (no real artifacts), no mock numbers in live')
// mock still available + clearly marked
await page.goto(base + '?transport=mock'); await page.waitForSelector('.cockpit')
ok(/DEV \/ MOCK/.test(await txt('.hdr')), 'M  mock mode carries the DEV / MOCK pill')
await page.evaluate(() => { location.hash = '/compare' }); await page.waitForSelector('.cmp'); await page.click('text=SHOW ALL'); await shot('e1-11-mock-compare', 1200)
const mc = await txt('.cmp')
ok(/LONG-HORIZON · MOCK/.test(mc) && /DEV \/ MOCK/.test(mc) && !/MIRAGE PPO/.test(mc), 'M  mock long-horizon lane labelled MOCK, never PPO')
await page.evaluate(() => { location.hash = '/benchmark' }); await page.waitForSelector('.lab'); await shot('e1-12-mock-lab')
ok(/DEV \/ MOCK DATA/.test(await txt('.lab')), 'M  mock lab carries the DEV / MOCK banner')
console.log('\nAPI calls (distinct):\n  ' + [...new Set(api)].join('\n  '))
const real = logs.filter(l => !/^warning:.*React Flow/.test(l))
console.log(real.length ? 'CONSOLE ISSUES:\n' + real.join('\n') : 'CONSOLE: no errors, no warnings')
console.log(failures ? `\nSMOKE FAILED: ${failures} checks` : '\nSMOKE PASSED')
await browser.close(); process.exit(failures ? 1 : 0)
