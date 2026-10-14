/* Mock-only regression: never run against real hardware. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),{execFileSync}=require('node:child_process'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const base=process.env.PIXELDOCK_UI_BASE||'http://127.0.0.1:8765';
if(!/^http:\/\/(127\.0\.0\.1|localhost):8765$/.test(base))throw Error('Mock-only test');
(async()=>{
 const fixture=path.join(process.env.RUNNER_TEMP|| (fs.existsSync('/tmp/opencode')?'/tmp/opencode':os.tmpdir()),'asset-editing-600.gif');
 execFileSync(process.env.PYTHON_PATH||(fs.existsSync('.venv/bin/python')?'.venv/bin/python':'python3'),['-c',`from PIL import Image
import sys
images=[Image.new('RGB',(32,8),'red' if i%2 else 'blue') for i in range(600)]
images[0].save(sys.argv[1],format='GIF',save_all=True,append_images=images[1:],duration=100)`,fixture]);
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||(fs.existsSync('/usr/bin/chromium')?'/usr/bin/chromium':undefined),headless:true,args:['--no-sandbox']});
 try{
 const context=await browser.newContext({viewport:{width:390,height:844}});
 const login=await context.request.post(base+'/api/auth/login',{data:{username:'admin',password:'local-ui-test-only'}});assert.equal(login.status(),200);
 const token=(await login.json()).access_token,headers={Authorization:`Bearer ${token}`};await context.addInitScript(t=>localStorage.setItem('token',t),token);
 const sourceName=`Trim smoke ${Date.now()}`,variantName=sourceName+' variant';
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>{errors.push(e.message);console.error('Browser error:',e.message);});
 await page.goto(base+'/studio');await page.locator('.asset-card').first().waitFor();
 const initial=(await(await context.request.get(base+'/api/assets',{headers})).json()).length;
 await page.locator('#importAsset [name="image"]').setInputFiles(fixture);
 await page.locator('#importAsset [name="name"]').fill(sourceName);
 await page.locator('#importAnalysis').filter({hasText:'600 Quellframes'}).waitFor();
 assert.equal(await page.locator('#importPreparation').getAttribute('open'),'');
 await page.locator('#importTrimControls [name="trim_start"]').fill('50');await page.locator('#importTrimControls [name="trim_end"]').fill('50');
 await page.locator('#importTrimControls [name="step"]').fill('2');
 await page.locator('#importTrimControls [data-trim-summary]').filter({hasText:'250 Frames'}).waitFor();
 await page.locator('#previewImportRange').click();await page.locator('#importRangeState').filter({hasText:'250 Frames · 50 s'}).waitFor();
 assert.equal((await(await context.request.get(base+'/api/assets',{headers})).json()).length,initial);
 await page.locator('#playImportRange').click();await page.locator('#playImportRange').filter({hasText:'Stopp'}).waitFor();await page.locator('#playImportRange').click();
 await page.locator('#importAsset button[type="submit"]').click();
 const card=page.locator('.asset-card').filter({has:page.getByRole('heading',{name:sourceName,exact:true})});await card.waitFor();
 await card.getByRole('button',{name:'Bearbeiten',exact:true}).click();
 await page.locator('#editorState').filter({hasText:'250 Frames'}).waitFor();
 await page.locator('#editorTrim summary').click();
 await page.locator('#editorTrimControls [name="trim_start"]').fill('10');await page.locator('#editorTrimControls [name="trim_end"]').fill('10');
 await page.locator('#applyTrim').click();
 await page.locator('#editorState').filter({hasText:'230 Frames'}).waitFor();
 await page.locator('#undoPixel').click();await page.locator('#editorState').filter({hasText:'250 Frames'}).waitFor();
 await page.locator('#editorTrimControls [name="range_kind"]').selectOption('time');
 await page.locator('#editorTrimControls [name="start_seconds"]').fill('1');await page.locator('#editorTrimControls [name="end_seconds"]').fill('3');
 await page.locator('#applyTrim').click();await page.locator('#editorState').filter({hasText:'10 Frames'}).waitFor();
 await page.locator('#spriteName').fill(variantName);await page.locator('#saveSprite').click();
 await page.getByRole('heading',{name:variantName,exact:true}).waitFor();
 const source=(await(await context.request.get(base+'/api/assets',{headers})).json()).find(v=>v.name===sourceName);assert.equal(source.frame_count,250);
 await card.getByRole('button',{name:'+ Playlist',exact:true}).click();
 await page.goto(base+'/modules');await page.locator('.module-card').first().waitFor();
 const module=page.locator('.module-card').filter({has:page.getByRole('heading',{name:sourceName,exact:true})});
 await module.locator('summary').first().click();assert.equal(await module.locator('[name="playback_mode"]').inputValue(),'limit');
 await module.locator('[name="playback_mode"]').selectOption('once');await module.locator('[name="speed"]').fill('2');
 assert.equal(await module.locator('[name="duration_seconds"]').isVisible(),false);
 await module.locator('[data-asset-timing]').filter({hasText:'25 s'}).waitFor();
 await module.getByRole('button',{name:'Speichern',exact:true}).click();await module.locator('.save-state').filter({hasText:'Gespeichert'}).waitFor();
 await page.reload();await page.locator('.module-card').first().waitFor();await module.locator('summary').first().click();
 assert.equal(await module.locator('[name="playback_mode"]').inputValue(),'once');
 await module.locator('[name="playback_mode"]').selectOption('finish_loop');assert.equal(await module.locator('[name="duration_seconds"]').isVisible(),true);
 await module.locator('[name="duration_seconds"]').fill('6');await module.locator('[data-asset-timing]').filter({hasText:'Wiedergabe: 25 s'}).waitFor();
 for(const width of [320,390,1280]){await page.setViewportSize({width,height:900});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
 assert.deepEqual(errors,[]);console.log('Asset editing smoke passed: overlong import, nonpersistent preview, trim, thinning, variable duration, undo, time selection, preserved original, playback modes and mobile layout.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
