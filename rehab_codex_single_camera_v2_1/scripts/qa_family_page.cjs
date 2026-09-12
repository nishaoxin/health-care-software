// Real browser/HTTP smoke test using an isolated loopback synthetic fixture.
// Run with bundled playwright on NODE_PATH; never uses the user's browser profile.
const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const { createInterface } = require('node:readline');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

async function main() {
  const root = path.resolve(__dirname, '..');
  const output = path.join(root, '.runtime', 'qa-silver-v016');
  fs.mkdirSync(output, { recursive: true });
  const fixture = spawn(path.join(root, '.venv', 'Scripts', 'python.exe'), ['-u', path.join(__dirname, 'qa_family_browser.py')], { cwd: root, windowsHide: true, stdio: ['pipe', 'pipe', 'inherit'] });
  let browser;
  const lines = createInterface({ input: fixture.stdout });
  const pending = [];
  const history = [];
  lines.on('line', line => { const data = JSON.parse(line); history.push(data); if (pending.length) pending.shift()(data); });
  const next = () => new Promise(resolve => pending.push(resolve));
  try {
    const info = await next();
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    const page = await browser.newPage({ viewport: { width: 390, height: 844 }, locale: 'zh-CN' });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(info.url);
    await page.screenshot({ path: path.join(output, 'phone-pair.png'), fullPage: true });
    await page.getByLabel('电脑显示的短时配对码').fill(info.code);
    await page.getByRole('button', { name: '申请配对', exact: true }).click();
    await page.getByText('等待电脑确认配对，尚不能读取资料', { exact: true }).waitFor();
    const approval = next(); fixture.stdin.write('approve\n'); await approval;
    await page.getByRole('button', { name: '我已查看', exact: true }).waitFor();
    await page.screenshot({ path: path.join(output, 'phone-request.png'), fullPage: true });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    await page.getByRole('button', { name: '我已查看', exact: true }).click();
    await page.getByRole('button', { name: '我来联系 / 处理', exact: true }).click();
    page.once('dialog', dialog => dialog.accept('TEST：已完成模拟联系，未进行实际求救。'));
    await page.getByRole('button', { name: '记录实际处理结果', exact: true }).click();
    await page.getByRole('heading', { name: '已记录处理结果', exact: true }).waitFor();
    await page.screenshot({ path: path.join(output, 'phone-resolved.png'), fullPage: true });
    const saved = next(); fixture.stdin.write('status\n');
    const final = await saved;
    assert.equal(final.requests[0].status, 'RESOLVED');
    assert.deepEqual(final.requests[0].history.map(h => h.action), ['ack', 'claim', 'resolve']);
    assert(final.requests[0].history.every(h => h.channel === 'LAN_FOREGROUND_TEST_ONLY'));
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(output, 'browser-result.json'), JSON.stringify({ passed: true, viewport: '390x844', origin: 'loopback-only', transitions: ['ACKNOWLEDGED', 'CLAIMED', 'RESOLVED'], pageErrors: errors }, null, 2));
    console.log('PASS: mobile-width browser pairing, desktop approval, ack, claim, resolve and SQLite receipts; no page errors.');
  } finally {
    if (browser) await browser.close();
    fixture.stdin.end('stop\n');
    lines.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
