// Collect real Acadza questions by driving the Practice DOST "Create Assignment" wizard as a normal user.
// Requires Edge running with --remote-debugging-port=9333 and an Acadza session already logged in.
// Usage: node collect_questions.js [outDir]
// For every free chapter x level it creates one assignment ("qbd-<chapter>-<level>") and saves the
// /next/practice/attempt response (full question JSON) to <outDir>/<chapter>__<level>.json
const path = require('path');
const fs = require('fs');
const { chromium } = require(process.env.PW_CORE || 'playwright-core');

const OUT = process.argv[2] || path.join(__dirname, '..', 'data', 'raw');
const CHAPTERS = ['Quadratic Equations', 'Sequences and Series (Progressions)', 'Binomial Theorem',
  'Permutation and Combination', 'Probability', 'Complex Numbers'];
const LEVELS = ['Easy', 'Medium', 'Hard'];
const MIX = { scq: 15, mcq: 5, integerQuestion: 5 };

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9333');
  const ctx = browser.contexts()[0];
  const page = ctx.pages().find(p => p.url().includes('acadza')) || ctx.pages()[0];
  const wait = ms => page.waitForTimeout(ms);
  const click = async (text, { exact = true, pause = 2500 } = {}) => {
    const ok = await page.evaluate(({ text, exact }) => {
      const norm = s => (s || '').trim().replace(/\s+/g, ' ').toLowerCase();
      const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
      let m = [...document.querySelectorAll('button,a,li,label,div,span,p,option')].filter(vis)
        .filter(e => exact ? norm(e.innerText) === norm(text) : norm(e.innerText).includes(norm(text)));
      m = m.filter(e => !m.some(o => o !== e && e.contains(o)));
      if (!m[0]) return false; m[0].scrollIntoView({ block: 'center' }); m[0].click(); return true;
    }, { text, exact });
    if (!ok) throw new Error('not found: ' + text);
    await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
    await wait(pause);
  };

  let captured = null;
  page.on('response', async r => {
    if (/\/next\/practice\/attempt/.test(r.url())) { try { captured = await r.text(); } catch (e) {} }
  });

  for (const chapter of CHAPTERS) {
    for (const level of LEVELS) {
      const file = path.join(OUT, `${chapter.replace(/[^a-z0-9]+/gi, '_')}__${level}.json`);
      if (fs.existsSync(file)) { console.log('skip (exists)', path.basename(file)); continue; }
      captured = null;
      try {
        await page.goto('https://www.acadza.com/dosts/practice/assignment/create', { waitUntil: 'domcontentloaded' });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {}); await wait(2500);
        await click('Math');
        await click(chapter);
        await click('Continue', { pause: 3000 });
        await click('Select Level of Assignment', { pause: 1200 });
        await click(level, { pause: 1200 });
        await click('Continue', { pause: 3000 });
        for (const [name, n] of Object.entries(MIX)) {
          const inp = page.locator(`input[name=${name}]`);
          if (await inp.count()) await inp.fill(String(n));
        }
        await page.fill('input[placeholder="Enter your assignment name"]', `qbd-${chapter.slice(0, 18)}-${level}`);
        await click('Create', { pause: 1000 });
        for (let i = 0; i < 30 && !captured; i++) await wait(1000);
        if (!captured) throw new Error('no attempt response captured');
        fs.writeFileSync(file, captured);
        const n = (JSON.parse(captured).questions || []).length;
        console.log(`ok ${chapter} / ${level}: ${n} questions`);
      } catch (e) {
        console.log(`ERR ${chapter} / ${level}: ${e.message.split('\n')[0]}`);
      }
    }
  }
  process.exit(0);
})();
