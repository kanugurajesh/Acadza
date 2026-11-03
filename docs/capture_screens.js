// Capture README screenshots and demo-GIF frames from app/review.html (headless Edge).
// Usage: node docs/capture_screens.js   then   .venv/Scripts/python -I docs/make_gif.py
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright-core');

const ROOT = path.resolve(__dirname, '..');
const OUT = path.join(__dirname, 'img');
const FRAMES = path.join(__dirname, 'frames');
const PAGE = 'file:///' + path.join(ROOT, 'app', 'review.html').replace(/\\/g, '/');

const OFF_CHAPTER = '6a4fc02abb8b1c4f072b02d7';  // off-chapter, judge sides with the Doctor
const VISION = process.env.QBD_VISION_ID || '60ec65b8b970c637a9f9ed01';  // untagged, maths was images
const KEY_DEFECT = '6a62745a9fc11309026096c9';   // two correct options in a single-correct question

async function pick(page, filter, id) {
  await page.selectOption('#filter', filter);
  const row = page.locator(`.row[data-id="${id}"]`);
  await row.scrollIntoViewIfNeeded();
  await row.click();
  await page.evaluate(() => { document.getElementById('detail').scrollTop = 0; });
  await page.waitForTimeout(600);  // KaTeX render
}

async function scrollDetailTo(page, heading) {
  await page.evaluate((h) => {
    const card = [...document.querySelectorAll('#detail .card h3')].find((e) => e.textContent.includes(h));
    if (card) document.getElementById('detail').scrollTop = card.parentElement.offsetTop - 70;
  }, heading);
  await page.waitForTimeout(200);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  fs.rmSync(FRAMES, { recursive: true, force: true });
  fs.mkdirSync(FRAMES, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 860 }, deviceScaleFactor: 1, colorScheme: 'light' });
  const page = await ctx.newPage();
  await page.goto(PAGE);
  await page.waitForFunction(() => window.renderMathInElement);

  // --- stills
  await pick(page, 'off_portion', OFF_CHAPTER);
  await page.screenshot({ path: path.join(OUT, 'review-off-chapter.png') });

  await pick(page, 'image', VISION);
  await page.screenshot({ path: path.join(OUT, 'review-image-maths.png') });

  // answer-key evidence: question + tags + key check in one crop, solutions hidden
  await pick(page, 'keywrong', KEY_DEFECT);
  await page.addStyleTag({ content: '#detail{max-height:none!important;overflow:visible!important} #detail > .cols:last-child{display:none}' });
  await page.locator('#detail').screenshot({ path: path.join(OUT, 'review-answer-key.png') });
  await page.reload(); await page.waitForFunction(() => window.renderMathInElement);

  await page.evaluate(() => { document.documentElement.dataset.theme = 'dark'; });
  await pick(page, 'off_portion', OFF_CHAPTER);
  await page.screenshot({ path: path.join(OUT, 'review-dark.png') });
  await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; });

  // --- demo frames: filter -> open -> evidence -> accept -> export
  let n = 0;
  const frame = async (hold) => page.screenshot({ path: path.join(FRAMES, `${String(n++).padStart(3, '0')}_${hold}.png`) });
  await page.selectOption('#filter', 'all');
  await page.evaluate(() => { document.getElementById('list').scrollTop = 0; document.getElementById('detail').innerHTML = '<p class="mute">Select a question.</p>'; });
  await frame(1400);
  await page.selectOption('#filter', 'off_portion'); await page.waitForTimeout(200); await frame(1300);
  await pick(page, 'off_portion', OFF_CHAPTER); await frame(2000);
  await scrollDetailTo(page, 'Tags'); await frame(2600);
  await page.click('#acc'); await page.waitForTimeout(200); await frame(1600);
  await pick(page, 'image', VISION); await frame(2400);
  await page.click('#acc'); await page.waitForTimeout(200); await frame(1400);
  await pick(page, 'keywrong', KEY_DEFECT); await scrollDetailTo(page, 'Answer key check'); await frame(2800);
  await page.locator('#export').hover(); await page.waitForTimeout(200); await frame(1800);

  await browser.close();
  console.log('stills ->', OUT, '| frames ->', FRAMES, `(${n})`);
})();
