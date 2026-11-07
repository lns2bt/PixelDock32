/* Playlist and pixel studio. No external scripts, fonts, or asset services. */
(() => {
  'use strict';
  if (!window.PixelDock) return;
  const { api, toast, matrix, bitcoinDuration, bitcoinDurationText, weatherDuration } = window.PixelDock;
  const $ = id => document.getElementById(id);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
  const guarded = fn => async event => { try { await fn(event); } catch (error) { toast(error.message, true); } };
  const json = (method, data) => ({ method, body: JSON.stringify(data) });
  const names = { clock:'Clock', btc:'Bitcoin', weather:'Weather & indoor climate', textbox:'Text', bitmap:'Bitmap', animations:'Animation', asset:'GIF / Sprite' };
  let modules = [], assets = [], dirty = false;
  const automaticBitcoin = row => row.key.split('-')[0] === 'btc' && row.settings?.bitcoin_stage !== false;
  const automaticWeather = row => row.key.split('-')[0] === 'weather' && row.settings?.weather_stage !== false;
  function durationLabel(row) { return automaticBitcoin(row)||automaticWeather(row) ? 'Automatic duration' : row.key.split('-')[0]==='asset'&&row.settings?.playback_mode==='once'?'A complete run':`${row.duration_seconds}s`; }
  function renderBitcoinTiming(row, container) {
    if (!automaticBitcoin(row)&&!automaticWeather(row)) return;
    (automaticWeather(row)?weatherDuration(row):bitcoinDuration(row)).then(timing => {
      if (!container.isConnected) return;
      container.querySelectorAll('[data-duration]').forEach(node => { node.textContent = bitcoinDurationText(timing); });
      const info = container.querySelector('[data-duration-info]');
      if (info) info.textContent = `${timing.info_count} Info${timing.info_count === 1 ? '' : 's'} · ${timing.read_seconds} s reading time per info${Number(timing.event_extra_seconds) > 0 ? ` · if necessary +${timing.event_extra_seconds} s block ceremony` : ''}. The performance runs through completely.`;
    }).catch(() => {
      if (!container.isConnected) return;
      const info = container.querySelector('[data-duration-info]');
      if (info) info.textContent = 'Automatic duration currently not available. Details on the stage page.';
    });
  }
  window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });

  // Dashboard stays intentionally quiet: useful values, no GPIO/protocol dumps.
  if (document.body.dataset.screen === 'dashboard') {
    window.addEventListener('pixeldock-status', ({ detail }) => {
      const data = detail.live_data;
      $('btcValue').textContent = data.btc_eur == null ? '—' : new Intl.NumberFormat('en-GB', { style:'currency', currency:'EUR', maximumFractionDigits:0 }).format(data.btc_eur);
      $('outValue').textContent = data.weather_outdoor_temp == null ? '—' : `${Number(data.weather_outdoor_temp).toFixed(1)} °C`;
      $('inValue').textContent = data.weather_indoor_temp == null ? '—' : `${Number(data.weather_indoor_temp).toFixed(1)} °C`;
      $('humidityValue').textContent = `humidity ${data.weather_indoor_humidity == null ? '—' : Math.round(data.weather_indoor_humidity) + ' %'}`;
    });
    $('quickText').onsubmit = guarded(async event => {
      event.preventDefault(); const values = new FormData(event.target);
      await api('/api/display/text', json('POST', { text:values.get('text'), seconds:Number(values.get('seconds')), font_size:'small' })); toast('Message is running.');
    });
    api('/api/modules').then(rows => {
      const active = rows.filter(row => row.enabled);
      $('dashboardModules').innerHTML = active.map(row => `<div class="mini-item"><span class="pill">${escape(names[row.key.split('-')[0]])}</span><strong class="grow">${escape(row.name)}</strong><span class="muted" data-duration>${escape(durationLabel(row))}</span><button type="button" data-play="${row.id}">▶</button></div>`).join('') || '<p class="muted">No active modules. Add something to your playlist.</p>';
      $('dashboardModules').querySelectorAll('.mini-item').forEach((card, index) => renderBitcoinTiming(active[index], card));
      $('dashboardModules').querySelectorAll('[data-play]').forEach(button => button.onclick = guarded(async () => { await api(`/api/modules/${button.dataset.play}/play`, { method:'POST' }); toast('Now playing.'); }));
    }).catch(error => toast(error.message, true));
  }

  function input(label, name, value, type = 'text', extra = '') {
    return `<label>${escape(label)}<input name="${name}" type="${type}" value="${escape(value)}" ${extra}></label>`;
  }
  function select(label, name, value, choices) {
    return `<label>${escape(label)}<select name="${name}">${choices.map(([key, title]) => `<option value="${escape(key)}" ${key === value ? 'selected' : ''}>${escape(title)}</option>`).join('')}</select></label>`;
  }
  function checkbox(label, name, value) { return `<label class="check"><input type="checkbox" name="${name}" ${value ? 'checked' : ''}>${escape(label)}</label>`; }
  function settingsFields(row) {
    const s = row.settings || {}, kind = row.key.split('-')[0];
    let html = input('Name', 'module_name', row.name, 'text', 'maxlength="100" required')
      + (automaticBitcoin(row)||automaticWeather(row) ? `<div class="automatic-duration"><strong data-duration>Automatic duration</strong><p class="muted" data-duration-info>Info and reading times are loading...</p><a href="/${automaticWeather(row)?'weather':'bitcoin'}">${automaticWeather(row)?'Weather':'Bitcoin'}-Stage einstellen</a><input type="hidden" name="duration_seconds" value="${escape(row.duration_seconds)}"></div>` : input('Duration (seconds)', 'duration_seconds', row.duration_seconds, 'number', 'min="1" max="300" required'))
      + select('transition', 'transition_effect', s.transition_effect || 'fade', [['fade','Gentle fade'],['dissolve','Soft pixel dissolve'],['slide','Vertical slide'],['push_left','Push left'],['push_right','Push right'],['wipe','Soft wipe'],['iris','Iris'],['morph','Pixel morph'],['glitch','Glitch'],['none','Without']])
      + input('Transition (ms)', 'transition_ms', s.transition_ms ?? 450, 'number', 'min="0" max="2000"')
      + input('Priority every … seconds (0 = off)', 'priority_every', s.priority_every ?? (kind === 'clock' ? 45 : 0), 'number', 'min="0" max="3600"')
      + checkbox('Random insertion instead of a fixed slot', 'shuffle', s.shuffle);
    if (kind === 'clock') {
      html += input('Timezone', 'timezone', s.timezone || 'Europe/Vienna')
        + input('Digit color', 'color', s.color || '#6ee1ff', 'color')
        + checkbox('Seconds on a classic clock', 'show_seconds', s.show_seconds ?? true);
      const variants = s.variants || ['classic','arcade','progress','orbit','neon','flip'];
      html += `<div class="wide"><p class="muted">Exactly one view per display. The next activated view only follows the next time the clock appears: </p><div class="editor-toolbar">${[['classic','Classic numbers'],['arcade','Arcade / Coin Runner'],['progress','Seconds progress'],['binary','Binary accents'],['orbit','Neon Orbit'],['neon','Neon numbers & star flight'],['flip','Pixel-Flip / Clockwork']].map(([key,title]) => checkbox(title, 'variant_' + key, variants.includes(key))).join('')}</div></div>`;
    } else if (kind === 'textbox') {
      html += `<label class="wide">Text / Lines<textarea name="lines" rows="3" maxlength="2000">${escape(s.lines || 'HELLO PIXELDOCK')}</textarea></label>`
        + select('Appearance', 'text_mode', s.text_mode || 'scroll', [['scroll','Scrolling text'],['static','Switch lines']])
        + input('Scroll speed (Pixel/s)', 'scroll_speed', s.scroll_speed || 35, 'number', 'min="5" max="120"')
        + input('Text color', 'color', s.color || '#f4f4f5', 'color');
    } else if (kind === 'animations') {
      html += select('Animation', 'preset', s.preset || 'bit_invaders', [['aurora','Aurora'],['ripple','Water Ripple'],['fireflies','Fireflies'],['sine_ribbons','Sine Ribbons'],['synthwave','Synthwave'],['embers','Embers'],['game_of_life','Game of Life'],['starfield','Starfield'],['bit_invaders','Pixel Invaders'],['pixel_snake','Pixel Snake'],['retro_rainbow_tunnel','Rainbow Tunnel'],['psychedelic_plasma','Plasma'],['neon_equalizer','Neon Equalizer'],['matrix_rain','Matrix Rain'],['lava_lamp','Lava Lamp']])
        + select('Palette', 'palette', s.palette || 'auto', [['auto','Automatic (matches the animation)'],['neon','Neon'],['rainbow','Rainbow'],['fire','Fire'],['ocean','Ocean'],['matrix','Matrix'],['aurora','Aurora'],['sunset','Sunset'],['ice','Ice'],['forest','Forest']])
        + select('Mirror', 'mirror_mode', s.mirror_mode || 'none', [['none','None'],['horizontal','Left ↔ right'],['vertical','Top ↕ bottom'],['quad','Kaleidoscope (both)']])
        + input('speed', 'speed', s.speed || 1, 'number', 'min="0.1" max="4" step="0.1"')
        + input('intensity', 'intensity', s.intensity || .8, 'number', 'min="0.1" max="1" step="0.1"');
    } else if (kind === 'asset') {
      html += select('Asset', 'asset_id', s.asset_id, assets.map(asset => [asset.id, asset.name]))
        + select('Playback mode','playback_mode',s.playback_mode||'limit',[['limit','Maximum duration'],['once','A complete run'],['finish_loop','Timeout + end loop']])
        + input('speed', 'speed', s.speed || 1, 'number', 'min="0.1" max="4" step="0.1"')
        + '<p class="wide muted" data-asset-timing></p>';
    } else if (kind === 'weather') {
      html += '<p class="wide muted">Four common scene styles for outdoor, indoor, humidity and current weather. <a href="/weather">Set weather stage and check live</a>.</p>';
      if (!automaticWeather(row)) html += input('Values ​​change every… seconds', 'screen_seconds', s.screen_seconds || 4, 'number', 'min="1" max="60"')
        + checkbox('Outside temperature', 'show_outdoor', s.show_outdoor ?? true)
        + checkbox('Room temperature', 'show_indoor', s.show_indoor ?? true)
        + checkbox('humidity', 'show_humidity', s.show_humidity ?? true)
        + '<p class="wide muted">All weather modules use the same configured location. Location change is done via WEATHER_LAT / WEATHER_LON in the system configuration.</p>';
    } else if (kind === 'btc') {
      html += '<p class="wide muted">New Bitcoin Stage: equal information, maximum two per presentation as standard. Set scenes, selection, rotation and previews on your own page: <a href="/bitcoin">Open Bitcoin Stage</a>. A performance that has started runs through completely.</p>'
        + input('Bitcoin symbol', 'color_b', s.color_b || '#ff8c00', 'color')
        + input('Price with rising trend', 'color_up', s.color_up || '#00c850', 'color')
        + input('Price in a falling trend', 'color_down', s.color_down || '#e63c3c', 'color')
        + input('Price with neutral trend', 'color_flat', s.color_flat || '#dcdc50', 'color')
        + '<p class="wide muted">The color fields apply to the old representation. New scenes use their tuned Bitcoin palettes.</p>';
    } else if (kind === 'bitmap') {
      html += input('File in the bitmap directory', 'file', s.file || 'sample_gradient.ppm')
        + select('Scroll direction', 'scroll_direction', s.scroll_direction || 'top_to_bottom', [['top_to_bottom','Top down'],['bottom_to_top','From bottom to top']])
        + input('Scroll speed', 'scroll_speed', s.scroll_speed || 2, 'number', 'min="0.25" max="20" step="0.25"');
    }
    return html;
  }

  function renderModules() {
    $('moduleList').innerHTML = modules.map((row,index) => `<article class="panel module-card ${row.enabled ? '' : 'disabled'}" data-id="${row.id}"><div class="module-head"><button class="drag-handle" draggable="true" aria-label="${escape(row.name)} move" type="button">⠿</button><div class="grow"><h2>${escape(row.name)}</h2><small>${escape(names[row.key.split('-')[0]])} · <span data-duration>${escape(durationLabel(row))}</span></small></div><button type="button" data-move="-1" aria-label="${escape(row.name)} up" ${index === 0 ? 'disabled' : ''}>↑</button><button type="button" data-move="1" aria-label="${escape(row.name)} downward" ${index === modules.length - 1 ? 'disabled' : ''}>↓</button><button type="button" data-action="play">▶ Now</button></div><form class="module-form">${checkbox('Active', 'enabled', row.enabled)}<details><summary>Settings & Playback</summary><div class="field-grid">${settingsFields(row)}</div><details><summary>Additional settings (JSON)</summary><p class="muted">For additional options of the existing modules. Form fields take precedence.</p><textarea name="settings_json" rows="5">${escape(JSON.stringify(row.settings, null, 2))}</textarea></details></details><div class="form-actions"><button class="primary" type="submit">Save</button><button type="button" data-action="duplicate">Duplicate</button>${row.key.includes('-') ? '<button type="button" class="danger" data-action="delete">Remove</button>' : ''}<span class="muted save-state" role="status"></span></div></form></article>`).join('');
    $('moduleList').querySelectorAll('.module-card').forEach(card => {
      const row = modules.find(item => item.id === Number(card.dataset.id)), form = card.querySelector('form');
      renderBitcoinTiming(row, card);
      function assetTiming() {
        if(row.key.split('-')[0]!=='asset')return;
        const asset=assets.find(a=>a.id===form.elements.asset_id.value),mode=form.elements.playback_mode.value;
        const duration=form.elements.duration_seconds,speed=Number(form.elements.speed.value)||1;
        duration.closest('label').hidden=mode==='once';duration.required=mode!=='once';
        const cycle=asset?asset.cycle_seconds/speed:0,limit=Number(duration.value)||row.duration_seconds;
        const actual=mode==='once'?cycle:mode==='finish_loop'&&cycle?Math.ceil(limit/cycle)*cycle:limit;
        card.querySelector('[data-asset-timing]').textContent=asset?`${asset.frame_count} Frames · ${asset.cycle_seconds.toLocaleString('en-GB')} s Source · ${cycle.toLocaleString('en-GB')} s per loop ${speed}× · Playback: ${actual.toLocaleString('en-GB')} s. ${mode==='limit'?'Hard time limit; short loops repeat.':mode==='once'?'Exactly once, duration automatic.':'End the loop you have started after the time limit.'}`:'Select asset.';
      }
      assetTiming();form.addEventListener('input',assetTiming);form.addEventListener('change',assetTiming);
      form.oninput = () => { card.classList.add('dirty'); card.querySelector('.save-state').textContent = 'Unsaved'; dirty = true; };
      form.onsubmit = guarded(async event => {
        event.preventDefault(); const data = new FormData(form);
        const settings = JSON.parse(data.get('settings_json'));
        if (!settings || Array.isArray(settings) || typeof settings !== 'object') throw new Error('Settings must be a JSON object');
        for (const element of form.elements) {
          if (!element.name || ['settings_json','enabled','duration_seconds','module_name'].includes(element.name) || element.name.startsWith('variant_')) continue;
          settings[element.name] = element.type === 'checkbox' ? element.checked : element.type === 'number' ? Number(element.value) : element.value;
        }
        if (row.key.split('-')[0] === 'clock') {
          settings.variants = [...form.querySelectorAll('[name^="variant_"]:checked')].map(el => el.name.slice(8));
          if (!settings.variants.length) throw new Error('Please activate at least one clock view');
        }
        const saved = await api(`/api/modules/${row.id}`, json('PUT', { name:data.get('module_name'), enabled:form.elements.enabled.checked, duration_seconds:Number(data.get('duration_seconds')), sort_order:row.sort_order, settings }));
        Object.assign(row, saved); card.classList.remove('dirty'); card.classList.toggle('disabled', !row.enabled); card.querySelector('.save-state').textContent = 'Saved';
        card.querySelector('h2').textContent = row.name;
        card.querySelector('.module-head small').innerHTML = `${escape(names[row.key.split('-')[0]])} · <span data-duration>${escape(durationLabel(row))}</span>`;
        renderBitcoinTiming(row, card);
        dirty = !!$('moduleList').querySelector('.dirty'); toast('Module saved.');
      });
      card.querySelectorAll('[data-move]').forEach(button => button.onclick = guarded(() => moveModule(row.id, modules.indexOf(row) + Number(button.dataset.move))));
      card.querySelectorAll('[data-action]').forEach(button => button.onclick = guarded(async () => {
        if (button.dataset.action === 'play') { await api(`/api/modules/${row.id}/play`, { method:'POST' }); toast('Playback started once.'); }
        if (button.dataset.action === 'duplicate') {
          if (!allowRefresh()) return;
          await api('/api/modules', json('POST', { kind:row.key.split('-')[0], name:(row.name + ' Copy').slice(0,100), duration_seconds:row.duration_seconds, settings:row.settings })); await loadModules();
        }
        if (button.dataset.action === 'delete' && allowRefresh() && confirm(`„${row.name}“ Remove from the playlist?`)) { await api(`/api/modules/${row.id}`, { method:'DELETE' }); await loadModules(); }
      }));
      const handle = card.querySelector('.drag-handle');
      handle.ondragstart = event => { event.dataTransfer.setData('text/plain', String(row.id)); card.classList.add('dragging'); };
      handle.ondragend = () => { card.classList.remove('dragging'); document.querySelectorAll('.drop-target').forEach(node => node.classList.remove('drop-target')); };
      card.ondragover = event => { event.preventDefault(); card.classList.add('drop-target'); };
      card.ondragleave = () => card.classList.remove('drop-target');
      card.ondrop = guarded(async event => { event.preventDefault(); card.classList.remove('drop-target'); await moveModule(Number(event.dataTransfer.getData('text/plain')), modules.indexOf(row)); });
    });
  }
  function allowRefresh() { return !dirty || confirm('Discard unsaved changes?'); }
  async function moveModule(id, target) {
    if (!allowRefresh()) return;
    const index = modules.findIndex(row => row.id === id);
    if (index < 0 || target < 0 || target >= modules.length || target === index) return;
    const ordered = [...modules]; ordered.splice(target, 0, ordered.splice(index,1)[0]);
    await api('/api/modules/order', json('PUT', { ids:ordered.map(row => row.id) })); await loadModules(); toast('Order saved.');
  }
  async function loadModules() {
    [modules, assets] = await Promise.all([api('/api/modules'), api('/api/assets')]); dirty = false; renderModules();
  }
  if (document.body.dataset.screen === 'playlist') {
    loadModules().catch(error => toast(error.message,true));
    $('addModule').onsubmit = guarded(async event => {
      event.preventDefault(); if (!allowRefresh()) return;
      const data = new FormData(event.target);
      await api('/api/modules', json('POST', { kind:data.get('kind'), name:data.get('name'), duration_seconds:data.get('kind') === 'clock' ? 8 : 10, settings:{} }));
      event.target.reset(); await loadModules(); toast('Added new module.');
    });
  }

  if (document.body.dataset.screen !== 'studio') return;
  function trimControls(node, durations, onChange) {
    node.innerHTML='<div class="field-grid">'+select('Selection','range_kind','frames',[['frames','Remove frames'],['time','Keep time range']])+input('Remove frames at the beginning','trim_start',0,'number','min="0" step="1"')+input('Remove frames at the end','trim_end',0,'number','min="0" step="1"')+input('Start time (seconds)','start_seconds',0,'number','min="0" step="0.001"')+input('End time (seconds; blank = end)','end_seconds','','number','min="0.001" step="0.001"')+input('Keep every... frame','step',1,'number','min="1" max="64" step="1"')+'</div><p data-trim-summary role="status"></p><div class="editor-toolbar"><div>Erster Frame<canvas data-first width="256" height="64" class="matrix-canvas"></canvas></div><div>Letzter Frame<canvas data-last width="256" height="64" class="matrix-canvas"></canvas></div></div>';
    const options=()=>Object.fromEntries([...node.querySelectorAll('input,select')].map(el=>[el.name,el.name==='range_kind'?el.value:el.name==='end_seconds'&&el.value===''?null:Number(el.value)]));
    function update(){const o=options();for(const el of node.querySelectorAll('input')){if(['trim_start','trim_end'].includes(el.name))el.closest('label').hidden=o.range_kind==='time';if(['start_seconds','end_seconds'].includes(el.name))el.closest('label').hidden=o.range_kind!=='time';}try{const p=AssetEditing.plan(durations(),o);node.querySelector('[data-trim-summary]').textContent=`${p.frame_count} Frames · ${(p.cycle_ms/1000).toLocaleString('en-GB')} s · removed: beginning ${p.removed_start_ms/1000} s/end ${p.removed_end_ms/1000} s · area ${p.start_ms/1000}–${p.end_ms/1000} s${p.frame_count>512?' · Too many frames: shorten or thin out!':''}`;onChange?.(p,o);}catch(e){node.querySelector('[data-trim-summary]').textContent=e.message;onChange?.(null,o);}}
    node.addEventListener('input',update);node.addEventListener('change',update);
    return {options,update,plan:()=>AssetEditing.plan(durations(),options()),reset:()=>{node.querySelectorAll('input').forEach(el=>el.value=el.name==='step'?1:el.name==='end_seconds'?'':0);node.querySelector('select').value='frames';update();}};
  }
  let frames = [{ pixels:Array(256).fill(0), duration_ms:100 }], current = 0, erasing = false, playing = false, painting = false, undo = [], previewTimer;
  const copy = () => JSON.parse(JSON.stringify(frames));
  function checkpoint() { undo.push({ frames:copy(), current }); if (undo.length > 30) undo.shift(); dirty = true; }
  function stopPreview() { playing = false; clearTimeout(previewTimer); $('previewSprite').textContent = '▶ Preview'; $('previewTrim').textContent='▶ Only play selection'; }
  function drawEditor() {
    matrix($('spriteCanvas'), frames[current].pixels, true, $('onionSkin').checked && current > 0 ? frames[current-1].pixels : null);
    $('frameDuration').value = frames[current].duration_ms;
    $('editorState').textContent = `${frames.length} Frame${frames.length === 1 ? '' : 's'} · ${frames.reduce((n, f) => n + f.duration_ms, 0)} ms per loop${dirty ? ' · unsaved draft' : ''}`;
    $('frameStrip').innerHTML = frames.map((_,i) => `<button type="button" class="frame-thumb ${i === current ? 'selected' : ''}" data-frame="${i}" aria-label="Frame ${i+1}" aria-pressed="${i === current}"><canvas width="128" height="32"></canvas>${i+1} · ${frames[i].duration_ms}ms</button>`).join('');
    $('frameStrip').querySelectorAll('button').forEach((button,i) => { matrix(button.querySelector('canvas'), frames[i].pixels); button.onclick = () => { stopPreview(); current = i; drawEditor(); }; });
    editorTrim.update();
  }
  function pointerPixel(event) {
    const bounds = $('spriteCanvas').getBoundingClientRect();
    const x = Math.floor((event.clientX - bounds.left) / bounds.width * 32), y = Math.floor((event.clientY - bounds.top) / bounds.height * 8);
    if (x < 0 || x >= 32 || y < 0 || y >= 8) return;
    frames[current].pixels[y*32+x] = erasing ? 0 : parseInt($('paintColor').value.slice(1),16);
    matrix($('spriteCanvas'), frames[current].pixels, true, $('onionSkin').checked && current > 0 ? frames[current-1].pixels : null);
  }
  $('spriteCanvas').onpointerdown = event => { stopPreview(); checkpoint(); painting = true; $('spriteCanvas').setPointerCapture(event.pointerId); pointerPixel(event); };
  $('spriteCanvas').onpointermove = event => { if (painting) pointerPixel(event); };
  $('spriteCanvas').onpointerup = $('spriteCanvas').onpointercancel = () => { painting = false; drawEditor(); };
  $('paintColor').oninput = () => { erasing = false; $('eraser').setAttribute('aria-pressed','false'); };
  $('eraser').onclick = () => { erasing = !erasing; $('eraser').setAttribute('aria-pressed',String(erasing)); };
  $('onionSkin').onchange = drawEditor;
  $('frameDuration').onchange = () => { const value = Number($('frameDuration').value); if (!Number.isInteger(value) || value < 33 || value > 2000) { toast('33-2000 ms required',true); drawEditor(); return; } checkpoint(); frames[current].duration_ms = value; drawEditor(); };
  $('undoPixel').onclick = () => { stopPreview(); const state = undo.pop(); if (state) { frames = state.frames; current = state.current; dirty = true; drawEditor(); } };
  $('clearFrame').onclick = () => { stopPreview(); checkpoint(); frames[current].pixels.fill(0); drawEditor(); };
  for (const [id,clone] of [['addFrame',false],['cloneFrame',true]]) $(id).onclick = () => {
    if (frames.length >= 512) { toast('Maximum 512 Frames',true); return; }
    stopPreview(); checkpoint(); frames.splice(current+1,0,{ pixels:clone ? [...frames[current].pixels] : Array(256).fill(0), duration_ms:frames[current].duration_ms }); current++; drawEditor();
  };
  $('deleteFrame').onclick = () => { if (frames.length === 1) return; stopPreview(); checkpoint(); frames.splice(current,1); current = Math.min(current,frames.length-1); drawEditor(); };
  for (const [id,delta] of [['moveFrameLeft',-1],['moveFrameRight',1]]) $(id).onclick = () => { const target = current+delta; if (target < 0 || target >= frames.length) return; stopPreview(); checkpoint(); [frames[current],frames[target]] = [frames[target],frames[current]]; current = target; drawEditor(); };
  $('previewSprite').onclick = () => {
    if (playing) { stopPreview(); drawEditor(); return; }
    playing = true; $('previewSprite').textContent = '■ Stop'; let index = 0;
    function tick() { if (!playing) return; matrix($('spriteCanvas'),frames[index].pixels,true); const delay = frames[index].duration_ms; index = (index+1)%frames.length; previewTimer = setTimeout(tick,delay); } tick();
  };
  $('newSprite').onclick = () => { if (dirty && !confirm('Discard current draft?')) return; stopPreview(); frames = [{pixels:Array(256).fill(0),duration_ms:100}]; current = 0; undo = []; dirty = false; $('spriteName').value = 'My sprite'; editorTrim.reset();drawEditor(); };
  $('spriteName').oninput = () => { dirty = true; };
  $('saveSprite').onclick = guarded(async () => {
    stopPreview(); const button = $('saveSprite'); button.disabled = true;
    try { await api('/api/assets/sprites',json('POST',{ name:$('spriteName').value, frames })); dirty = false; drawEditor(); await loadAssets(); toast('Saved to library. Add now as a module.'); } finally { button.disabled = false; }
  });
  let importedFrames = null, importedStarted = 0;
  function showImported(data) {
    importedFrames = data.frames; importedStarted = performance.now(); $('importPreview').hidden = false;
    const canvas = $('importPreview').querySelector('canvas');
    function tick() {
      if (!importedFrames) return;
      const cycle = importedFrames.reduce((n,f) => n+f.duration_ms,0); let t = (performance.now()-importedStarted)%cycle, selected = importedFrames[0];
      for (const frame of importedFrames) { selected = frame; if (t < frame.duration_ms) break; t -= frame.duration_ms; }
      if (!document.hidden) matrix(canvas,selected.pixels); setTimeout(tick,50);
    }
    if (!showImported.started) { showImported.started = true; tick(); }
  }
  const editorTrim=trimControls($('editorTrimControls'),()=>frames.map(f=>f.duration_ms),(p)=>{if(!p)return;matrix($('editorTrimControls').querySelector('[data-first]'),frames[p.groups[0].index].pixels);matrix($('editorTrimControls').querySelector('[data-last]'),frames[p.groups.at(-1).index].pixels);});
  $('editorTrimControls').addEventListener('input',stopPreview);
  $('previewTrim').onclick=guarded(()=>{if(playing){stopPreview();drawEditor();return;}const p=editorTrim.plan();stopPreview();playing=true;$('previewTrim').textContent='■ Stopp';let index=0;function tick(){if(!playing)return;const group=p.groups[index];matrix($('spriteCanvas'),frames[group.index].pixels,true);index=(index+1)%p.groups.length;previewTimer=setTimeout(tick,group.duration_ms);}tick();});
  $('editorTrim').addEventListener('toggle',()=>{if(!$('editorTrim').open){stopPreview();drawEditor();}});
  $('applyTrim').onclick=guarded(()=>{const p=editorTrim.plan();if(p.frame_count>512)throw Error('Maximum 512 Frames');stopPreview();checkpoint();frames=p.groups.map(g=>({pixels:[...frames[g.index].pixels],duration_ms:g.duration_ms}));current=0;editorTrim.reset();drawEditor();toast('Area applied to draft. Original remains intact.');});
  const importForm=$('importAsset'),prepare=document.createElement('details');prepare.id='importPreparation';prepare.innerHTML='<summary>Prepare import: shorten / thin out</summary><p id="importAnalysis">Select file.</p><div id="importTrimControls"></div><button id="previewImportRange" type="button">Selection as animation check</button><button id="playImportRange" type="button" disabled>▶ Play selection</button><p id="importRangeState" role="status"></p>';
  importForm.after(prepare);
  let analysis=null,analyzedFile=null,analysisRevision=0,importFrames=null,importPlaying=false,importTimer=null,importIndex=0,importRevision=0;
  function stopImport(){importPlaying=false;clearTimeout(importTimer);$('playImportRange').textContent='▶ Play selection';}
  function invalidateImport(){importRevision++;stopImport();importFrames=null;$('playImportRange').disabled=true;$('importRangeState').textContent='Reload preview after changes.';}
  const importTrim=trimControls($('importTrimControls'),()=>analysis?.durations_ms||[],invalidateImport);
  importForm.elements.fit.onchange=invalidateImport;
  async function analyzeFile(file){const revision=++analysisRevision;analysis=null;analyzedFile=null;stopImport();$('importAnalysis').textContent='File is being analyzed...';if(file.size>4*1024*1024)throw Error('Maximum 4 MB');const result=await api('/api/assets/analyze',{method:'POST',body:file,headers:{'Content-Type':file.type||'application/octet-stream'}});if(revision!==analysisRevision)return;analysis=result;analyzedFile=file;importTrim.reset();$('importAnalysis').textContent=`${result.width} × ${result.height} · ${result.frame_count} source frames · ${result.cycle_seconds.toLocaleString('en-GB')} s. Finished asset: maximum 512 frames. Time ranges are expanded to full frames.`;if(result.frame_count>512)prepare.open=true;}
  importForm.elements.image.onchange=()=>{const file=importForm.elements.image.files[0];if(file)analyzeFile(file).catch(e=>toast(e.message,true));};
  async function importSelection(preview=false){const values=new FormData(importForm),file=importForm.elements.image.files[0];if(!file?.size)throw Error('Select file');if(analyzedFile!==file){await analyzeFile(file);if(analyzedFile!==file)throw Error('Please wait for analysis');}const p=importTrim.plan();if(p.frame_count>512)throw Error('Selection has more than 512 frames; shorten or thin out.');const params=new URLSearchParams({name:values.get('name')||'Import',fit:values.get('fit'),preview:String(preview),...Object.fromEntries(Object.entries(importTrim.options()).filter(([,v])=>v!==null))});return api(`/api/assets/import?${params}`,{method:'POST',body:file,headers:{'Content-Type':file.type||'application/octet-stream'}});}
  $('previewImportRange').onclick=guarded(async()=>{stopImport();const revision=importRevision,button=$('previewImportRange');button.disabled=true;try{const data=await importSelection(true);if(revision!==importRevision)return;importFrames=data.frames;importIndex=0;matrix($('importTrimControls').querySelector('[data-first]'),importFrames[0].pixels);matrix($('importTrimControls').querySelector('[data-last]'),importFrames.at(-1).pixels);$('playImportRange').disabled=false;$('importRangeState').textContent=`Browser preview · ${importFrames.length} Frames · ${data.cycle_seconds} s · not yet saved`;}finally{button.disabled=false;}});
  $('playImportRange').onclick=()=>{if(importPlaying){stopImport();return;}if(!importFrames)return;importPlaying=true;$('playImportRange').textContent='■ Stopp';function tick(){if(!importPlaying)return;matrix($('importTrimControls').querySelector('[data-first]'),importFrames[importIndex].pixels);const delay=importFrames[importIndex].duration_ms;importIndex=(importIndex+1)%importFrames.length;importTimer=setTimeout(tick,delay);}tick();};
  prepare.addEventListener('toggle',()=>{if(!prepare.open)stopImport();});document.addEventListener('visibilitychange',()=>{if(document.hidden){stopImport();stopPreview();}});
  $('importAsset').onsubmit = guarded(async event => {
    event.preventDefault(); const form = event.target, values = new FormData(form), file = values.get('image'), button = form.querySelector('button');
    if (file.size > 4*1024*1024) throw new Error('Maximum 4 MB');
    button.disabled = true;
    try { const data = await importSelection(); showImported(data); await loadAssets(); toast('Imported. Check the preview and add the asset.'); } finally { button.disabled = false; }
  });
  async function loadAssets() {
    assets = await api('/api/assets');
    $('assetLibrary').innerHTML = assets.map(asset => `<article class="panel asset-card" data-id="${escape(asset.id)}"><canvas width="512" height="128" class="matrix-canvas" aria-label="${escape(asset.name)} Preview"></canvas><h3>${escape(asset.name)}</h3><p class="muted">${asset.frame_count} Frames · ${asset.cycle_seconds.toFixed(2)}s per Loop</p><div class="form-actions"><button type="button" data-action="add" class="primary">+ Playlist</button><button type="button" data-action="play">▶ Now</button><button type="button" data-action="edit">Edit</button>${asset.id.startsWith('demo_') ? '' : '<button type="button" data-action="delete" class="danger">Delete</button>'}</div></article>`).join('');
    $('assetLibrary').querySelectorAll('.asset-card').forEach(card => {
      const asset = assets.find(row => row.id === card.dataset.id); matrix(card.querySelector('canvas'),asset.preview);
      card.querySelectorAll('[data-action]').forEach(button => button.onclick = guarded(async () => {
        button.disabled = true;
        try {
          const action = button.dataset.action;
          if (action === 'add') { await api('/api/modules',json('POST',{kind:'asset',name:asset.name,duration_seconds:10,settings:{asset_id:asset.id,transition_effect:'fade'}})); toast('Added to playlist.'); }
          if (action === 'play') {
            // Reuse or create a disabled slot so "Now" never silently changes the playlist.
            let rows = await api('/api/modules'), row = rows.find(row => row.settings.asset_id === asset.id);
            if (!row) {
              row = await api('/api/modules',json('POST',{kind:'asset',name:asset.name,enabled:false,duration_seconds:10,settings:{asset_id:asset.id}}));
            }
            await api(`/api/modules/${row.id}/play`,{method:'POST'}); toast('Play once. Then playlist again.');
          }
          if (action === 'edit') {
            if (dirty && !confirm('Discard current draft?')) return;
            const data = await api(`/api/assets/${asset.id}`); stopPreview(); frames = data.frames; current = 0; undo = []; dirty = false; $('spriteName').value = data.name; editorTrim.reset();drawEditor(); document.querySelector('.editor-panel').scrollIntoView({block:'start'});
          }
          if (action === 'delete' && confirm(`„${asset.name}" delete?`)) { await api(`/api/assets/${asset.id}`,{method:'DELETE'}); await loadAssets(); }
        } finally { button.disabled = false; }
      }));
    });
  }
  $('reloadAssets').onclick = guarded(loadAssets);
  drawEditor(); loadAssets().catch(error => toast(error.message,true));
})();
