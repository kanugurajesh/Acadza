// Render each question that stores maths as <img> fragments into ONE screenshot, so the vision model
// reads the whole question (with context) in a single call instead of one call per tiny fragment.
// Usage: node render_questions.js data/audit.json data/render
// Needs Edge on CDP port 9333 (any page; a fresh tab is opened and closed).
const fs = require('fs');
const path = require('path');
const { chromium } = require(process.env.PW_CORE || 'playwright-core');

(async () => {
  const [auditPath, outDir] = process.argv.slice(2);
  fs.mkdirSync(outDir, { recursive: true });
  const rows = JSON.parse(fs.readFileSync(auditPath, 'utf8'));
  const todo = [];
  for (const r of rows) {
    if (r.q_images.length) todo.push({ id: r._id, part: 'q', html: r.question_html });
    if (r.s_images.length) todo.push({ id: r._id, part: 's', html: r.solution_html });
  }
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9333');
  const page = await browser.contexts()[0].newPage();
  await page.setViewportSize({ width: 900, height: 600 });
  let done = 0;
  for (const t of todo) {
    const file = path.join(outDir, `${t.id}_${t.part}.png`);
    if (fs.existsSync(file)) { done++; continue; }
    await page.setContent(`<!doctype html><html><head><meta charset="utf-8"><style>
      body{margin:0;background:#fff;font:20px/1.6 "Times New Roman",serif;color:#000}
      #q{display:inline-block;padding:14px 18px;max-width:860px}
      #q h3,#q p{font:inherit;margin:0} #q img{vertical-align:middle;transform-origin:left center}
    </style></head><body><div id="q">${t.html}</div></body></html>`, { waitUntil: 'load', timeout: 30000 }).catch(() => {});
    // enlarge the tiny formula fragments ~1.6x so the model can read them
    await page.evaluate(() => document.querySelectorAll('#q img').forEach(i => {
      if (i.naturalHeight && i.naturalHeight < 40) { i.style.height = (i.naturalHeight * 1.6) + 'px'; i.style.width = 'auto'; }
    }));
    await page.waitForTimeout(150);
    await page.locator('#q').screenshot({ path: file });
    done++;
  }
  console.log(`rendered ${done}/${todo.length} parts into ${outDir}`);
  await page.close();
  process.exit(0);
})();
