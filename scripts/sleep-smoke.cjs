/* Mutating regression checks: localhost mock fixture only, never the physical Pi. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require('playwright');
const base = process.env.BASE_URL || 'http://127.0.0.1:8765';
assert.ok(/^http:\/\/(127\.0\.0\.1|localhost):8765$/.test(base), 'Use the mock fixture on port 8765');

(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_PATH || (fs.existsSync('/usr/bin/chromium') ? '/usr/bin/chromium' : undefined), args:['--no-sandbox']});
  try {
    const context = await browser.newContext({viewport:{width:375,height:812},hasTouch:true,isMobile:true});
    const page = await context.newPage();
    await page.goto(base + '/login');
    const login = await context.request.post(base + '/api/auth/login', {data:{username:'admin',password:'local-ui-test-only'}});
    assert.equal(login.status(), 200);
    const token = (await login.json()).access_token;
    await page.evaluate(token => localStorage.setItem('token',token), token);
    const headers = {Authorization:`Bearer ${token}`};
    const metrics = await (await context.request.get(base+'/api/debug/led/metrics',{headers})).json();
    assert.equal(metrics.result.transport,'mock','Refusing test against real hardware');
    const get = async () => (await context.request.get(base+'/api/time-stage',{headers})).json();
    const initial = await get();
    const config = structuredClone(initial.config);
    config.sleep = {...config.sleep,start:'02:00',end:'08:00',mode:'auto',until:null};
    await context.request.put(base+'/api/time-stage',{headers,data:config});
    await page.goto(base+'/time-stage#night');
    await page.locator('#timeStageFields:not([disabled])').waitFor();
    const running = (await (await context.request.get(base+'/api/version')).json()).version;
    assert.equal(running, fs.readFileSync('VERSION','utf8').trim());
    await page.locator('#activeVersion').filter({hasText:'v'+running}).waitFor();
    // Move an actual slider by keyboard, then verify the exact payload and reload.
    await page.locator('#sleepStartRange').focus();
    await page.keyboard.press('Home');
    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('ArrowRight');
    assert.equal(await page.locator('#sleep_start').inputValue(),'00:10');
    assert.equal(await page.locator('#sleep_end').inputValue(),'08:00');
    const request = page.waitForRequest(r=>r.url()===base+'/api/time-stage'&&r.method()==='PUT');
    await page.locator('#saveTimeStage').click();
    assert.equal((await request).postDataJSON().sleep.start,'00:10');
    await page.locator('#dirtyState').filter({hasText:'Saved and verified.'}).waitFor();
    assert.equal((await get()).config.sleep.start,'00:10');
    await page.reload();
    await page.locator('#timeStageFields:not([disabled])').waitFor();
    assert.equal(await page.locator('#sleep_start').inputValue(),'00:10');
    // Exact minute entry must not be rounded by moving the OTHER slider.
    await page.locator('#sleep_start').fill('02:03');
    await page.locator('#sleepEndRange').focus();
    await page.keyboard.press('ArrowRight');
    assert.equal(await page.locator('#sleep_start').inputValue(),'02:03');
    assert.equal(await page.locator('#sleep_end').inputValue(),'08:05');
    await page.locator('#saveTimeStage').click();
    await page.locator('#dirtyState').filter({hasText:'Saved and verified.'}).waitFor();
    // Another tab changes the plan: stale writes fail, without losing local edits.
    const other = await get(); other.config.sleep.end='09:15';
    await context.request.put(base+'/api/time-stage',{headers:{...headers,'If-Match':other.revision},data:other.config});
    await page.locator('#sleep_end').fill('07:30');
    const conflict=page.waitForResponse(r=>r.url()===base+'/api/time-stage'&&r.request().method()==='PUT');
    await page.locator('#saveTimeStage').click();
    assert.equal((await conflict).status(),409);
    assert.equal(await page.locator('#sleep_end').inputValue(),'07:30');
    assert.equal((await get()).config.sleep.end,'09:15');
    // Simulate an incorrect server acknowledgement; never report success.
    await page.reload();
    await page.locator('#timeStageFields:not([disabled])').waitFor();
    await page.locator('#sleep_end').fill('07:45');
    await page.route('**/api/time-stage',async route=>{
      if(route.request().method()!=='PUT')return route.continue();
      const result=await get();result.config.sleep.end='17:37';
      await route.fulfill({json:result});
    });
    await page.locator('#saveTimeStage').click();
    await page.locator('#timeStageFeedback.error').filter({hasText:'Saved sleep times differ'}).waitFor();
    assert.equal(await page.locator('#sleep_end').inputValue(),'07:45');
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile sleep controls overflow');
    await context.close();
    console.log('Sleep smoke passed: slider/save/reload, minute precision, stale tabs, mismatch detection and active version.');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
