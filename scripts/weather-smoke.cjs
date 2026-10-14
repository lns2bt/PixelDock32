/* MOCK ONLY. Fixed loopback origin + transport guard run before any mutation. Never target a Pi. */
const {chromium} = require('playwright');
const assert = require('node:assert/strict'), fs = require('node:fs');
const base = 'http://127.0.0.1:8765';
(async () => {
  assert.equal(new URL(base).hostname, '127.0.0.1');
  assert.equal(new URL(base).port, '8765');
  const browser = await chromium.launch({executablePath:process.env.CHROMIUM_PATH || (fs.existsSync('/usr/bin/chromium') ? '/usr/bin/chromium' : undefined),headless:true,args:['--no-sandbox']});
  let context, headers, original, sleepConfig;
  try {
    context = await browser.newContext({viewport:{width:390,height:844}});
    const login = await context.request.post(base + '/api/auth/login',{data:{username:'admin',password:'local-ui-test-only'}});
    assert.equal(login.status(),200);
    const token = (await login.json()).access_token; headers = {Authorization:`Bearer ${token}`};
    const metrics = await context.request.get(base + '/api/debug/led/metrics',{headers});
    assert.equal(metrics.status(),200);
    assert.equal((await metrics.json()).result.transport,'mock','Refusing to test non-mock LEDs');
    await context.addInitScript(value => localStorage.setItem('token',value),token);
    const catalogResponse = await context.request.get(base + '/api/weather',{headers}); assert.equal(catalogResponse.status(),200);
    const catalog = await catalogResponse.json();
    assert.equal(catalog.styles.length,4); assert.equal(catalog.infos.length,4);
    const modules = async () => (await context.request.get(base + '/api/modules',{headers})).json();
    original = (await modules()).find(value => value.key?.split('-')[0] === 'weather'); assert.ok(original,'Mock fixture needs a weather module');
    // Controlled defaults, plus unknown legacy settings that must survive a full-row save.
    const fixture = {...original,settings:{legacy_weather_smoke:{preserve:true},show_outdoor:true,show_indoor:true,show_humidity:true}};
    assert.equal((await context.request.put(base + `/api/modules/${original.id}`,{headers,data:fixture})).status(),200);
    const before = (await modules()).find(value => value.id === original.id);
    const page = await context.newPage(), errors = [], dialogs = [], previews = [], writes = [];
    page.on('pageerror',error => errors.push(error.message));
    page.on('dialog',async dialog => { dialogs.push(dialog.type()); await dialog.dismiss(); });
    page.on('request',request => {
      if (request.url().endsWith('/api/weather/preview')) previews.push({payload:request.postDataJSON(),at:Date.now()});
      if (request.method() === 'PUT' && request.url().includes('/api/modules/')) writes.push(request.postDataJSON());
    });
    await page.goto(base + '/weather'); await page.locator('#weatherFields:not([disabled])').waitFor();
    assert.ok(await page.locator('.live-header').isVisible());
    assert.equal(await page.locator('#weather_stage').isChecked(),true);
    assert.equal(await page.locator('#weather_max_infos').inputValue(),'2');
    assert.equal(await page.locator('#weather_read_seconds').inputValue(),'4');
    assert.equal(await page.locator('#weatherInfos input:checked').count(),4);
    assert.equal(await page.locator('#weatherStyles input:checked').count(),4);
    assert.equal(await page.locator('#weatherSavebar').isVisible(),false);
    assert.equal(await page.locator('main > details[open], #weatherFields > details[open]').count(),0);
    await page.locator('#weatherDuration').filter({hasText:'Automatisch'}).waitFor();
    await page.locator('#weatherBrowserPreview > summary').click();
    await page.locator('#weatherDemo').check(); await page.locator('#weatherCondition').selectOption('95'); await page.locator('#weatherIsDay').uncheck();
    await page.locator('#weatherSnapshot').click();
    await page.locator('#weatherPreviewStatus').filter({hasText:'Nacht'}).waitFor();
    assert.ok(previews.some(value => !value.payload.physical && value.payload.demo && value.payload.condition === 95 && value.payload.is_day === false));
    assert.deepEqual((await modules()).find(value => value.id === original.id),before);
    assert.equal(writes.length,0);
    await page.locator('#weather_max_infos').fill('3'); await page.locator('#weather_read_seconds').fill('5');
    await page.locator('#weather_info_order').selectOption('shuffle'); await page.locator('#weather_style_order').selectOption('shuffle');
    await page.locator('#weatherInfos').locator('..').locator('summary').first().click();
    await page.locator('[data-info="outside"] input').uncheck();
    await page.locator('[data-info="inside"] [data-move="-1"]').click();
    assert.equal(await page.locator('#weatherSavebar').isVisible(),true);
    await page.locator('#weatherStyles').locator('..').locator('summary').first().click();
    const physicalRequest = page.waitForRequest(request => request.url().endsWith('/api/weather/preview') && request.postDataJSON()?.physical);
    await page.locator('[data-led-style]').first().click();
    const physical = (await physicalRequest).postDataJSON();
    assert.equal(physical.physical,true); assert.equal(physical.demo,false); assert.equal(physical.info,null); assert.equal(physical.elapsed,0);
    assert.equal(Object.hasOwn(physical,'condition'),false); assert.equal(Object.hasOwn(physical,'is_day'),false);
    assert.equal(physical.settings.weather_max_infos,3); assert.equal(physical.settings.weather_read_seconds,5);
    assert.equal(physical.settings.show_outdoor,false); assert.equal(physical.settings.show_indoor,true); assert.equal(physical.settings.show_humidity,true);
    assert.deepEqual(physical.settings.legacy_weather_smoke,{preserve:true});
    await page.locator('#weatherLedStatus').filter({hasText:'LED-Vorschau gestartet'}).waitFor();
    assert.deepEqual((await modules()).find(value => value.id === original.id),before); assert.equal(writes.length,0);
    await page.locator('#weatherPreviewInfo').selectOption('inside');
    const globalRequest = page.waitForRequest(request => request.url().endsWith('/api/weather/preview') && request.postDataJSON()?.physical);
    await page.locator('#weatherPhysical').click(); const global = (await globalRequest).postDataJSON();
    assert.equal(global.info,'inside'); assert.equal(global.demo,false); assert.equal(Object.hasOwn(global,'condition'),false); assert.equal(Object.hasOwn(global,'is_day'),false);
    await page.locator('#weatherPreviewStatus').filter({hasText:'LED-Vorschau gestartet'}).waitFor();
    await page.locator('#weatherDemo').uncheck();
    const liveRequest = page.waitForRequest(request => request.url().endsWith('/api/weather/preview') && !request.postDataJSON()?.physical);
    await page.locator('#weatherSnapshot').click(); const live = (await liveRequest).postDataJSON();
    assert.equal(live.demo,false); assert.equal(Object.hasOwn(live,'condition'),false); assert.equal(Object.hasOwn(live,'is_day'),false);
    await page.locator('#weatherPreviewStatus').filter({hasText:'Live-Daten'}).waitFor();
    await page.locator('#weatherPreviewPlay').click(); await page.waitForTimeout(1100);
    await page.locator('#weatherBrowserPreview > summary').click(); await page.waitForTimeout(350);
    const closedCount = previews.length; await page.waitForTimeout(600); assert.equal(previews.length,closedCount,'Closed preview must stop');
    for (let i = 1; i < previews.length; i++) assert.ok(previews[i].at - previews[i-1].at >= 225,'Preview requests exceed 4 fps');
    await page.locator('#saveWeather').click(); await page.locator('#weatherFeedback').filter({hasText:'Gespeichert.'}).waitFor();
    assert.equal(writes.length,1); assert.equal(await page.locator('#weatherSavebar').isVisible(),false);
    const saved = (await modules()).find(value => value.id === original.id);
    assert.equal(saved.settings.weather_max_infos,3); assert.equal(saved.settings.weather_read_seconds,5);
    assert.equal(saved.settings.weather_info_order,'shuffle'); assert.equal(saved.settings.weather_style_order,'shuffle');
    assert.equal(saved.settings.show_outdoor,false); assert.equal(saved.settings.weather_infos.includes('outside'),false);
    assert.deepEqual(saved.settings.legacy_weather_smoke,{preserve:true});
    for (const key of ['name','enabled','duration_seconds','sort_order']) assert.deepEqual(saved[key],before[key]);
    // Sleep is exercised only after the mock transport guard; always restore its config.
    sleepConfig = (await (await context.request.get(base + '/api/time-stage',{headers})).json()).config;
    assert.equal((await context.request.post(base + '/api/time-stage/sleep',{headers,data:{mode:'sleep'}})).status(),200);
    await page.locator('#weatherBrowserPreview > summary').click();
    const sleepingResponse = page.waitForResponse(response => response.url().endsWith('/api/weather/preview') && response.request().postDataJSON()?.physical);
    await page.locator('#weatherPhysical').click(); assert.equal((await sleepingResponse).status(),409);
    await page.locator('#weatherPreviewStatus').filter({hasText:'Wach'}).waitFor();
    assert.equal((await context.request.put(base + '/api/time-stage',{headers,data:sleepConfig})).status(),200); sleepConfig = undefined;
    await page.reload(); await page.locator('#weatherFields:not([disabled])').waitFor();
    assert.equal(await page.locator('#weather_max_infos').inputValue(),'3'); assert.equal(await page.locator('#weather_read_seconds').inputValue(),'5');
    assert.equal(await page.locator('#weatherSavebar').isVisible(),false);
    for (const width of [320,390]) {
      await page.setViewportSize({width,height:900});
      await page.locator('main details').evaluateAll(nodes => nodes.forEach(node => { node.open = true; }));
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),`Weather page overflow at ${width}px`);
      assert.ok(await page.locator('#weatherPhysical').evaluate(node => node.getBoundingClientRect().height >= 44));
    }
    assert.deepEqual(dialogs,[]); assert.deepEqual(errors,[]);
    console.log('Weather mock smoke passed: catalog defaults, compact accordions, dirty save, unsaved real LED previews, browser demo/night, sleep guard, serialization, save/reload, mobile widths.');
  } finally {
    try {
      if (sleepConfig) await context.request.put(base + '/api/time-stage',{headers,data:sleepConfig});
      if (original) await context.request.put(base + `/api/modules/${original.id}`,{headers,data:original});
    } finally { await browser.close(); }
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
