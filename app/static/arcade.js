/* Playlist and pixel studio. No external scripts, fonts, or asset services. */
(() => {
  'use strict';
  if (!window.PixelDock) return;
  const { api, toast, matrix } = window.PixelDock;
  const $ = id => document.getElementById(id);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
  const guarded = fn => async event => { try { await fn(event); } catch (error) { toast(error.message, true); } };
  const json = (method, data) => ({ method, body: JSON.stringify(data) });
  const names = { clock:'Uhr', btc:'Bitcoin', weather:'Wetter & Raumklima', textbox:'Text', bitmap:'Bitmap', animations:'Animation', asset:'GIF / Sprite' };
  let modules = [], assets = [], dirty = false;
  window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });

  // Dashboard stays intentionally quiet: useful values, no GPIO/protocol dumps.
  if (document.body.dataset.screen === 'dashboard') {
    window.addEventListener('pixeldock-status', ({ detail }) => {
      const data = detail.live_data;
      $('btcValue').textContent = data.btc_eur == null ? '—' : new Intl.NumberFormat('de-AT', { style:'currency', currency:'EUR', maximumFractionDigits:0 }).format(data.btc_eur);
      $('outValue').textContent = data.weather_outdoor_temp == null ? '—' : `${Number(data.weather_outdoor_temp).toFixed(1)} °C`;
      $('inValue').textContent = data.weather_indoor_temp == null ? '—' : `${Number(data.weather_indoor_temp).toFixed(1)} °C`;
      $('humidityValue').textContent = `Luftfeuchtigkeit ${data.weather_indoor_humidity == null ? '—' : Math.round(data.weather_indoor_humidity) + ' %'}`;
    });
    $('quickText').onsubmit = guarded(async event => {
      event.preventDefault(); const values = new FormData(event.target);
      await api('/api/display/text', json('POST', { text:values.get('text'), seconds:Number(values.get('seconds')), font_size:'small' })); toast('Nachricht läuft.');
    });
    api('/api/modules').then(rows => {
      $('dashboardModules').innerHTML = rows.filter(row => row.enabled).map(row => `<div class="mini-item"><span class="pill">${escape(names[row.key.split('-')[0]])}</span><strong class="grow">${escape(row.name)}</strong><span class="muted">${row.duration_seconds}s</span><button type="button" data-play="${row.id}">▶</button></div>`).join('') || '<p class="muted">Keine aktiven Module. Füge deiner Playlist etwas hinzu.</p>';
      $('dashboardModules').querySelectorAll('[data-play]').forEach(button => button.onclick = guarded(async () => { await api(`/api/modules/${button.dataset.play}/play`, { method:'POST' }); toast('Wird jetzt abgespielt.'); }));
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
      + input('Dauer (Sekunden)', 'duration_seconds', row.duration_seconds, 'number', 'min="1" max="300" required')
      + select('Übergang', 'transition_effect', s.transition_effect || 'fade', [['fade','Sanfter Fade'],['dissolve','Pixel-Dissolve'],['slide','Slide'],['none','Ohne']])
      + input('Übergang (ms)', 'transition_ms', s.transition_ms ?? 450, 'number', 'min="0" max="2000"')
      + input('Priorität alle … Sekunden (0 = aus)', 'priority_every', s.priority_every ?? (kind === 'clock' ? 45 : 0), 'number', 'min="0" max="3600"')
      + checkbox('Zufälliger Einwurf statt festem Slot', 'shuffle', s.shuffle);
    if (kind === 'clock') {
      html += input('Zeitzone', 'timezone', s.timezone || 'Europe/Vienna')
        + input('Ziffernfarbe', 'color', s.color || '#6ee1ff', 'color')
        + checkbox('Sekunden bei klassischer Uhr', 'show_seconds', s.show_seconds ?? true);
      const variants = s.variants || ['classic','arcade','progress','orbit','neon','flip'];
      html += `<div class="wide"><p class="muted">Genau eine Ansicht pro Einblendung. Erst beim nächsten Uhr-Auftritt folgt die nächste aktivierte Ansicht:</p><div class="editor-toolbar">${[['classic','Klassische Ziffern'],['arcade','Arcade / Coin Runner'],['progress','Sekunden-Fortschritt'],['binary','Binär-Akzente'],['orbit','Neon-Orbit'],['neon','Neon-Ziffern & Sternenflug'],['flip','Pixel-Flip / Clockwork']].map(([key,title]) => checkbox(title, 'variant_' + key, variants.includes(key))).join('')}</div></div>`;
    } else if (kind === 'textbox') {
      html += `<label class="wide">Text / Zeilen<textarea name="lines" rows="3" maxlength="2000">${escape(s.lines || 'HELLO PIXELDOCK')}</textarea></label>`
        + select('Darstellung', 'text_mode', s.text_mode || 'scroll', [['scroll','Laufschrift'],['static','Zeilen wechseln']])
        + input('Scrolltempo (Pixel/s)', 'scroll_speed', s.scroll_speed || 35, 'number', 'min="5" max="120"')
        + input('Textfarbe', 'color', s.color || '#f4f4f5', 'color');
    } else if (kind === 'animations') {
      html += select('Animation', 'preset', s.preset || 'bit_invaders', [['bit_invaders','Pixel Invaders'],['pixel_snake','Pixel Snake'],['retro_rainbow_tunnel','Rainbow Tunnel'],['psychedelic_plasma','Plasma'],['neon_equalizer','Neon Equalizer'],['matrix_rain','Matrix Rain'],['lava_lamp','Lava Lamp']])
        + select('Palette', 'palette', s.palette || 'neon', [['neon','Neon'],['rainbow','Rainbow'],['fire','Fire'],['ocean','Ocean'],['matrix','Matrix']])
        + input('Geschwindigkeit', 'speed', s.speed || 1, 'number', 'min="0.1" max="4" step="0.1"')
        + input('Intensität', 'intensity', s.intensity || .8, 'number', 'min="0.1" max="1" step="0.1"');
    } else if (kind === 'asset') {
      html += select('Asset', 'asset_id', s.asset_id, assets.map(asset => [asset.id, asset.name]))
        + input('Geschwindigkeit', 'speed', s.speed || 1, 'number', 'min="0.1" max="4" step="0.1"')
        + '<p class="wide muted">Die Slot-Dauer wird bis zum Ende des begonnenen Animationsloops verlängert.</p>';
    } else if (kind === 'weather') {
      html += input('Werte wechseln alle … Sekunden', 'screen_seconds', s.screen_seconds || 4, 'number', 'min="1" max="60"')
        + checkbox('Außentemperatur', 'show_outdoor', s.show_outdoor ?? true)
        + checkbox('Raumtemperatur', 'show_indoor', s.show_indoor ?? true)
        + checkbox('Luftfeuchtigkeit', 'show_humidity', s.show_humidity ?? true)
        + '<p class="wide muted">Alle Wettermodule nutzen denselben konfigurierten Standort. Standortwechsel erfolgt über WEATHER_LAT / WEATHER_LON in der Systemkonfiguration.</p>';
    } else if (kind === 'btc') {
      html += checkbox('Zusätzlich Blockhöhe anzeigen', 'show_block_height', s.show_block_height)
        + input('Werte wechseln alle … Sekunden', 'screen_seconds', s.screen_seconds || 4, 'number', 'min="1" max="60"')
        + input('Bitcoin-Symbol', 'color_b', s.color_b || '#ff8c00', 'color')
        + input('Preis bei steigendem Trend', 'color_up', s.color_up || '#00c850', 'color')
        + input('Preis bei fallendem Trend', 'color_down', s.color_down || '#e63c3c', 'color')
        + input('Preis bei neutralem Trend', 'color_flat', s.color_flat || '#dcdc50', 'color')
        + '<p class="wide muted">Das ₿-Symbol pulsiert unabhängig von der Preisfarbe. k = tausend Euro, M = Millionen Euro; Trendfarbe und Pfeil zeigen die Richtung.</p>';
    } else if (kind === 'bitmap') {
      html += input('Datei im Bitmap-Verzeichnis', 'file', s.file || 'sample_gradient.ppm')
        + select('Scrollrichtung', 'scroll_direction', s.scroll_direction || 'top_to_bottom', [['top_to_bottom','Von oben nach unten'],['bottom_to_top','Von unten nach oben']])
        + input('Scrolltempo', 'scroll_speed', s.scroll_speed || 2, 'number', 'min="0.25" max="20" step="0.25"');
    }
    return html;
  }

  function renderModules() {
    $('moduleList').innerHTML = modules.map((row,index) => `<article class="panel module-card ${row.enabled ? '' : 'disabled'}" data-id="${row.id}"><div class="module-head"><button class="drag-handle" draggable="true" aria-label="${escape(row.name)} verschieben" type="button">⠿</button><div class="grow"><h2>${escape(row.name)}</h2><small>${escape(names[row.key.split('-')[0]])} · ${row.duration_seconds}s</small></div><button type="button" data-move="-1" aria-label="${escape(row.name)} nach oben" ${index === 0 ? 'disabled' : ''}>↑</button><button type="button" data-move="1" aria-label="${escape(row.name)} nach unten" ${index === modules.length - 1 ? 'disabled' : ''}>↓</button><button type="button" data-action="play">▶ Jetzt</button></div><form class="module-form">${checkbox('Aktiv', 'enabled', row.enabled)}<details><summary>Einstellungen & Wiedergabe</summary><div class="field-grid">${settingsFields(row)}</div><details><summary>Weitere Einstellungen (JSON)</summary><p class="muted">Für zusätzliche Optionen der bestehenden Module. Formularfelder haben Vorrang.</p><textarea name="settings_json" rows="5">${escape(JSON.stringify(row.settings, null, 2))}</textarea></details></details><div class="form-actions"><button class="primary" type="submit">Speichern</button><button type="button" data-action="duplicate">Duplizieren</button>${row.key.includes('-') ? '<button type="button" class="danger" data-action="delete">Entfernen</button>' : ''}<span class="muted save-state" role="status"></span></div></form></article>`).join('');
    $('moduleList').querySelectorAll('.module-card').forEach(card => {
      const row = modules.find(item => item.id === Number(card.dataset.id)), form = card.querySelector('form');
      form.oninput = () => { card.classList.add('dirty'); card.querySelector('.save-state').textContent = 'Ungespeichert'; dirty = true; };
      form.onsubmit = guarded(async event => {
        event.preventDefault(); const data = new FormData(form);
        const settings = JSON.parse(data.get('settings_json'));
        if (!settings || Array.isArray(settings) || typeof settings !== 'object') throw new Error('Einstellungen müssen ein JSON-Objekt sein');
        for (const element of form.elements) {
          if (!element.name || ['settings_json','enabled','duration_seconds','module_name'].includes(element.name) || element.name.startsWith('variant_')) continue;
          settings[element.name] = element.type === 'checkbox' ? element.checked : element.type === 'number' ? Number(element.value) : element.value;
        }
        if (row.key.split('-')[0] === 'clock') {
          settings.variants = [...form.querySelectorAll('[name^="variant_"]:checked')].map(el => el.name.slice(8));
          if (!settings.variants.length) throw new Error('Bitte mindestens eine Uhransicht aktivieren');
        }
        const saved = await api(`/api/modules/${row.id}`, json('PUT', { name:data.get('module_name'), enabled:form.elements.enabled.checked, duration_seconds:Number(data.get('duration_seconds')), sort_order:row.sort_order, settings }));
        Object.assign(row, saved); card.classList.remove('dirty'); card.classList.toggle('disabled', !row.enabled); card.querySelector('.save-state').textContent = 'Gespeichert';
        card.querySelector('h2').textContent = row.name;
        card.querySelector('.module-head small').textContent = `${names[row.key.split('-')[0]]} · ${row.duration_seconds}s`;
        dirty = !!$('moduleList').querySelector('.dirty'); toast('Modul gespeichert.');
      });
      card.querySelectorAll('[data-move]').forEach(button => button.onclick = guarded(() => moveModule(row.id, modules.indexOf(row) + Number(button.dataset.move))));
      card.querySelectorAll('[data-action]').forEach(button => button.onclick = guarded(async () => {
        if (button.dataset.action === 'play') { await api(`/api/modules/${row.id}/play`, { method:'POST' }); toast('Einmalige Wiedergabe gestartet.'); }
        if (button.dataset.action === 'duplicate') {
          if (!allowRefresh()) return;
          await api('/api/modules', json('POST', { kind:row.key.split('-')[0], name:(row.name + ' Kopie').slice(0,100), duration_seconds:row.duration_seconds, settings:row.settings })); await loadModules();
        }
        if (button.dataset.action === 'delete' && allowRefresh() && confirm(`„${row.name}“ aus der Playlist entfernen?`)) { await api(`/api/modules/${row.id}`, { method:'DELETE' }); await loadModules(); }
      }));
      const handle = card.querySelector('.drag-handle');
      handle.ondragstart = event => { event.dataTransfer.setData('text/plain', String(row.id)); card.classList.add('dragging'); };
      handle.ondragend = () => { card.classList.remove('dragging'); document.querySelectorAll('.drop-target').forEach(node => node.classList.remove('drop-target')); };
      card.ondragover = event => { event.preventDefault(); card.classList.add('drop-target'); };
      card.ondragleave = () => card.classList.remove('drop-target');
      card.ondrop = guarded(async event => { event.preventDefault(); card.classList.remove('drop-target'); await moveModule(Number(event.dataTransfer.getData('text/plain')), modules.indexOf(row)); });
    });
  }
  function allowRefresh() { return !dirty || confirm('Ungespeicherte Änderungen verwerfen?'); }
  async function moveModule(id, target) {
    if (!allowRefresh()) return;
    const index = modules.findIndex(row => row.id === id);
    if (index < 0 || target < 0 || target >= modules.length || target === index) return;
    const ordered = [...modules]; ordered.splice(target, 0, ordered.splice(index,1)[0]);
    await api('/api/modules/order', json('PUT', { ids:ordered.map(row => row.id) })); await loadModules(); toast('Reihenfolge gespeichert.');
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
      event.target.reset(); await loadModules(); toast('Neues Modul hinzugefügt.');
    });
  }

  if (document.body.dataset.screen !== 'studio') return;
  let frames = [{ pixels:Array(256).fill(0), duration_ms:100 }], current = 0, erasing = false, playing = false, painting = false, undo = [], previewTimer;
  const copy = () => JSON.parse(JSON.stringify(frames));
  function checkpoint() { undo.push({ frames:copy(), current }); if (undo.length > 30) undo.shift(); dirty = true; }
  function stopPreview() { playing = false; clearTimeout(previewTimer); $('previewSprite').textContent = '▶ Vorschau'; }
  function drawEditor() {
    matrix($('spriteCanvas'), frames[current].pixels, true, $('onionSkin').checked && current > 0 ? frames[current-1].pixels : null);
    $('frameDuration').value = frames[current].duration_ms;
    $('editorState').textContent = `${frames.length} Frame${frames.length === 1 ? '' : 's'} · ${frames.reduce((n, f) => n + f.duration_ms, 0)} ms pro Loop${dirty ? ' · ungespeicherter Entwurf' : ''}`;
    $('frameStrip').innerHTML = frames.map((_,i) => `<button type="button" class="frame-thumb ${i === current ? 'selected' : ''}" data-frame="${i}" aria-label="Frame ${i+1}" aria-pressed="${i === current}"><canvas width="128" height="32"></canvas>${i+1} · ${frames[i].duration_ms}ms</button>`).join('');
    $('frameStrip').querySelectorAll('button').forEach((button,i) => { matrix(button.querySelector('canvas'), frames[i].pixels); button.onclick = () => { stopPreview(); current = i; drawEditor(); }; });
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
  $('frameDuration').onchange = () => { const value = Number($('frameDuration').value); if (!Number.isInteger(value) || value < 33 || value > 2000) { toast('33–2000 ms erforderlich',true); drawEditor(); return; } checkpoint(); frames[current].duration_ms = value; drawEditor(); };
  $('undoPixel').onclick = () => { stopPreview(); const state = undo.pop(); if (state) { frames = state.frames; current = state.current; dirty = true; drawEditor(); } };
  $('clearFrame').onclick = () => { stopPreview(); checkpoint(); frames[current].pixels.fill(0); drawEditor(); };
  for (const [id,clone] of [['addFrame',false],['cloneFrame',true]]) $(id).onclick = () => {
    if (frames.length >= 120) { toast('Maximal 120 Frames',true); return; }
    stopPreview(); checkpoint(); frames.splice(current+1,0,{ pixels:clone ? [...frames[current].pixels] : Array(256).fill(0), duration_ms:frames[current].duration_ms }); current++; drawEditor();
  };
  $('deleteFrame').onclick = () => { if (frames.length === 1) return; stopPreview(); checkpoint(); frames.splice(current,1); current = Math.min(current,frames.length-1); drawEditor(); };
  for (const [id,delta] of [['moveFrameLeft',-1],['moveFrameRight',1]]) $(id).onclick = () => { const target = current+delta; if (target < 0 || target >= frames.length) return; stopPreview(); checkpoint(); [frames[current],frames[target]] = [frames[target],frames[current]]; current = target; drawEditor(); };
  $('previewSprite').onclick = () => {
    if (playing) { stopPreview(); drawEditor(); return; }
    playing = true; $('previewSprite').textContent = '■ Stop'; let index = 0;
    function tick() { if (!playing) return; matrix($('spriteCanvas'),frames[index].pixels,true); const delay = frames[index].duration_ms; index = (index+1)%frames.length; previewTimer = setTimeout(tick,delay); } tick();
  };
  $('newSprite').onclick = () => { if (dirty && !confirm('Aktuellen Entwurf verwerfen?')) return; stopPreview(); frames = [{pixels:Array(256).fill(0),duration_ms:100}]; current = 0; undo = []; dirty = false; $('spriteName').value = 'Mein Sprite'; drawEditor(); };
  $('spriteName').oninput = () => { dirty = true; };
  $('saveSprite').onclick = guarded(async () => {
    stopPreview(); const button = $('saveSprite'); button.disabled = true;
    try { await api('/api/assets/sprites',json('POST',{ name:$('spriteName').value, frames })); dirty = false; drawEditor(); await loadAssets(); toast('In Bibliothek gespeichert. Jetzt als Modul hinzufügen.'); } finally { button.disabled = false; }
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
  $('importAsset').onsubmit = guarded(async event => {
    event.preventDefault(); const form = event.target, values = new FormData(form), file = values.get('image'), button = form.querySelector('button');
    if (file.size > 4*1024*1024) throw new Error('Maximal 4 MB');
    button.disabled = true;
    try { const data = await api(`/api/assets/import?name=${encodeURIComponent(values.get('name'))}&fit=${values.get('fit')}`, { method:'POST', body:file, headers:{ 'Content-Type':file.type || 'application/octet-stream' } }); showImported(data); await loadAssets(); toast('Importiert. Prüfe die Vorschau und füge das Asset hinzu.'); } finally { button.disabled = false; }
  });
  async function loadAssets() {
    assets = await api('/api/assets');
    $('assetLibrary').innerHTML = assets.map(asset => `<article class="panel asset-card" data-id="${escape(asset.id)}"><canvas width="512" height="128" class="matrix-canvas" aria-label="${escape(asset.name)} Vorschau"></canvas><h3>${escape(asset.name)}</h3><p class="muted">${asset.frame_count} Frames · ${asset.cycle_seconds.toFixed(2)}s pro Loop</p><div class="form-actions"><button type="button" data-action="add" class="primary">+ Playlist</button><button type="button" data-action="play">▶ Jetzt</button><button type="button" data-action="edit">Bearbeiten</button>${asset.id.startsWith('demo_') ? '' : '<button type="button" data-action="delete" class="danger">Löschen</button>'}</div></article>`).join('');
    $('assetLibrary').querySelectorAll('.asset-card').forEach(card => {
      const asset = assets.find(row => row.id === card.dataset.id); matrix(card.querySelector('canvas'),asset.preview);
      card.querySelectorAll('[data-action]').forEach(button => button.onclick = guarded(async () => {
        button.disabled = true;
        try {
          const action = button.dataset.action;
          if (action === 'add') { await api('/api/modules',json('POST',{kind:'asset',name:asset.name,duration_seconds:10,settings:{asset_id:asset.id,transition_effect:'fade'}})); toast('Zur Playlist hinzugefügt.'); }
          if (action === 'play') {
            // Reuse or create a disabled slot so "Now" never silently changes the playlist.
            let rows = await api('/api/modules'), row = rows.find(row => row.settings.asset_id === asset.id);
            if (!row) {
              row = await api('/api/modules',json('POST',{kind:'asset',name:asset.name,enabled:false,duration_seconds:10,settings:{asset_id:asset.id}}));
            }
            await api(`/api/modules/${row.id}/play`,{method:'POST'}); toast('Einmalige Wiedergabe. Danach wieder Playlist.');
          }
          if (action === 'edit') {
            if (dirty && !confirm('Aktuellen Entwurf verwerfen?')) return;
            const data = await api(`/api/assets/${asset.id}`); stopPreview(); frames = data.frames; current = 0; undo = []; dirty = false; $('spriteName').value = data.name; drawEditor(); document.querySelector('.editor-panel').scrollIntoView({block:'start'});
          }
          if (action === 'delete' && confirm(`„${asset.name}“ löschen?`)) { await api(`/api/assets/${asset.id}`,{method:'DELETE'}); await loadAssets(); }
        } finally { button.disabled = false; }
      }));
    });
  }
  $('reloadAssets').onclick = guarded(loadAssets);
  drawEditor(); loadAssets().catch(error => toast(error.message,true));
})();
