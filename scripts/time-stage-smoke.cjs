/* Read-only browser check for the generated gallery. Requires Playwright. */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({executablePath:process.env.CHROMIUM_PATH || (fs.existsSync('/usr/bin/chromium') ? '/usr/bin/chromium' : undefined), headless:true,args:['--no-sandbox']});
  try {
    const context = await browser.newContext({viewport:{width:390,height:844}});
    const page = await context.newPage(), errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(process.env.TIME_STAGE_URL || 'http://127.0.0.1:8767/index.html');
    assert.equal(await page.locator('article').count(),30);
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.locator('img').first().waitFor();
    await page.waitForFunction(()=>{const img=document.querySelector('img');return img.complete&&img.naturalWidth===320;});
    await page.getByRole('button',{name:'20 Uhransichten',exact:true}).click();
    assert.equal(await page.locator('article:visible').count(),20);
    await page.getByRole('button',{name:'10 Ereignisse',exact:true}).click();
    assert.equal(await page.locator('article:visible').count(),10);
    await page.getByRole('button',{name:'Animationen pausieren',exact:true}).click();
    assert.ok(await page.locator('img').first().evaluate(img=>img.src.endsWith('.png')));
    await page.getByRole('button',{name:'Animationen fortsetzen',exact:true}).click();
    assert.ok(await page.locator('img').first().evaluate(img=>img.src.endsWith('.gif')));
    assert.deepEqual(errors,[]);
    const reduced=await browser.newContext({viewport:{width:1280,height:900},reducedMotion:'reduce'});
    const still=await reduced.newPage();
    await still.goto(process.env.TIME_STAGE_URL || 'http://127.0.0.1:8767/index.html');
    assert.ok(await still.locator('img').first().evaluate(img=>img.src.endsWith('.png')));
    await reduced.close();
    console.log('Time-Stage gallery passed: 30 scenes, filters, mobile layout, animation toggle, reduced motion.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
