/* Requires Playwright and the local mock fixture from ui-test-server.py. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({ executablePath:process.env.CHROMIUM_PATH || (fs.existsSync('/usr/bin/chromium') ? '/usr/bin/chromium' : undefined), headless:true, args:['--no-sandbox'] });
  try {
    const context = await browser.newContext({ viewport:{width:1280,height:900} });
    const base = 'http://127.0.0.1:8765';
    const response = await context.request.post(base + '/api/auth/login', {data:{username:'admin',password:'local-ui-test-only'}});
    assert.equal(response.status(),200);
    const token = (await response.json()).access_token, headers = {Authorization:`Bearer ${token}`};
    const metrics = await (await context.request.get(base + '/api/debug/led/metrics',{headers})).json();
    assert.equal(metrics.result.transport,'mock','Refusing UI test against real hardware');
    await context.addInitScript(value => localStorage.setItem('token',value), token);
    const page = await context.newPage(), errors = [], suffix = Date.now();
    const clockName = 'UI Clock ' + suffix, spriteName = 'UI Sprite ' + suffix;
    page.on('pageerror', error => errors.push(error.message));
    async function screenshot(name) {
      if (!process.env.PIXELDOCK_UI_ARTIFACTS) return;
      fs.mkdirSync(process.env.PIXELDOCK_UI_ARTIFACTS,{recursive:true});
      await page.screenshot({path:path.join(process.env.PIXELDOCK_UI_ARTIFACTS,name + '.png'),fullPage:true});
    }
    await page.goto(base + '/');
    await page.locator('.mini-item').first().waitFor();
    await screenshot('dashboard-desktop');
    await page.goto(base + '/modules');
    const first = page.locator('.module-card').first();
    await first.locator('summary').first().click();
    await first.locator('input[name="priority_every"]').fill('30');
    await first.getByRole('button',{name:'Speichern',exact:true}).click();
    await first.locator('.save-state').filter({hasText:'Gespeichert'}).waitFor();
    await page.locator('#addModule input[name="name"]').fill(clockName);
    await page.locator('#addModule button').click();
    await page.getByRole('heading',{name:clockName,exact:true}).waitFor();
    await page.getByRole('button',{name:clockName + ' nach oben',exact:true}).click();
    await page.locator('.module-card').filter({hasText:clockName}).waitFor();
    await page.evaluate(() => window.scrollTo(0,document.body.scrollHeight));
    assert.ok(Math.abs(await page.locator('.live-header').evaluate(el => el.getBoundingClientRect().top)) < 1);
    await page.setViewportSize({width:390,height:844});
    await page.goto(base + '/studio');
    await page.locator('.asset-card').first().waitFor();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),'Mobile page overflow');
    await screenshot('studio-mobile');
    // A valid GIF89a: exercises the actual upload form and client-side preview.
    const gif = Buffer.from('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7','base64');
    await page.locator('#importAsset input[type=file]').setInputFiles({name:'tiny.gif',mimeType:'image/gif',buffer:gif});
    await page.locator('#importAsset input[name=name]').fill('UI GIF ' + suffix);
    await page.locator('#importAsset button').click();
    await page.locator('#importPreview').waitFor({state:'visible'});
    await page.locator('#spriteCanvas').scrollIntoViewIfNeeded();
    const bounds = await page.locator('#spriteCanvas').boundingBox();
    await page.mouse.click(bounds.x+15,bounds.y+15);
    await page.locator('#cloneFrame').click();
    assert.equal(await page.locator('.frame-thumb').count(),2);
    await page.locator('#spriteName').fill(spriteName);
    await page.locator('#saveSprite').click();
    await page.getByRole('heading',{name:spriteName,exact:true}).waitFor();
    const card = page.locator('.asset-card').filter({has:page.getByRole('heading',{name:spriteName,exact:true})});
    await card.getByRole('button',{name:'+ Playlist',exact:true}).click();
    await page.locator('.retro-toast').filter({hasText:'Zur Playlist hinzugefügt'}).waitFor();
    const demo = page.locator('.asset-card').filter({has:page.getByRole('heading',{name:'Starship Patrol',exact:true})});
    await demo.getByRole('button',{name:'▶ Jetzt',exact:true}).click();
    await page.locator('.retro-toast').filter({hasText:'Einmalige Wiedergabe'}).waitFor();
    const rows = await (await context.request.get(base + '/api/modules',{headers})).json();
    assert.equal(rows.find(row => row.name === 'Starship Patrol').enabled,false);
    assert.equal(rows.find(row => row.key === 'clock').settings.priority_every,30);
    for (const route of ['/advanced','/debug','/mapping','/tools']) {
      await page.goto(base + route); await page.locator('.live-header').waitFor();
    }
    assert.deepEqual(errors,[]);
    console.log('UI smoke passed: desktop/mobile, sticky preview, settings/order, GIF upload, sprite editor/library, one-shot playback, diagnostics.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
