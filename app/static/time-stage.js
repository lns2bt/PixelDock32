/* Browser-test hooks: timeStageForm, timeStageFields, saveTimeStage,
 * timeStageFeedback, dirtyState, sceneList [data-scene-key], eventList
 * [data-category], sleep_start/end, sleepStartRange/sleepEndRange, sleepStrip,
 * sleepNow/wakeNow/sleepAuto/sleepTwoHours, previewScene/At/Time/Elapsed/Speed,
 * previewPlay/Snapshot/Physical, timeStageCanvas, exportTimeStage/importTimeStage.
 * GET never writes; previews use physical:false unless explicitly confirmed.
 */
(() => {
  'use strict';
  if (!window.PixelDock) return;
  const { api, matrix } = window.PixelDock;
  const $ = id => document.getElementById(id);
  const base = '/api/time-stage';
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
  const clone = value => JSON.parse(JSON.stringify(value));
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const categories = {
    hour:'Volle Stunde', half:'Halbe Stunde', quarter:'Viertelstunde', midnight:'Mitternacht',
    sunrise:'Sonnenaufgang', sunset:'Sonnenuntergang', moonrise:'Mondaufgang', moonset:'Monduntergang',
    golden_hour:'Goldene Stunde', solar_noon:'Sonnenhöchststand', full_moon:'Vollmond', new_moon:'Neumond', equinox:'Tagundnachtgleiche', solstice:'Sonnenwende'
  };
  const skyLabels = { sunrise:'Sonnenaufgang', sunset:'Sonnenuntergang', moonrise:'Mondaufgang', moonset:'Monduntergang', golden_hour:'Goldene Stunde', solar_noon:'Sonnenhöchststand', full_moon:'Vollmond', new_moon:'Neumond', equinox:'Tagundnachtgleiche', solstice:'Sonnenwende', moon_phase:'Mondphase', illumination:'Mondbeleuchtung', latitude:'Breitengrad', longitude:'Längengrad', source:'Quelle', updated_at:'Berechnet am', cached_at:'Im Cache seit', timezone:'Zeitzone' };
  const scalarFields = ['timezone','profile','intensity','selection'];
  const numberFields = ['after_entries','interval_seconds','duration_seconds','event_grace_seconds'];
  const checkFields = ['enabled','avoid_style_repeat','minute_transition'];
  let original = null, catalog = [], sceneOrder = [], selected = new Set(), favorites = new Set(), weights = {}, dirty = false, status = {}, busy = false;
  const changedEvents = new Set();
  let playing = false, timer = null, previewBusy = false, previewController = null, generation = 0;
  let clockAnchor = Date.now(), elapsedAnchor = 0, motionAnchor = performance.now();
  let lastPixels = '';
  let latestSnapshot = {};
  function feedback(text, error = false) { $('timeStageFeedback').textContent = text; $('timeStageFeedback').classList.toggle('error', error); }
  function markDirty() { dirty = true; $('dirtyState').textContent = 'Ungespeicherte Änderungen.'; }
  function plain(value) { return value == null ? 'Nicht verfügbar' : object(value) || Array.isArray(value) ? JSON.stringify(value) : String(value); }
  function addDefinition(list, title, value) { const dt = document.createElement('dt'), dd = document.createElement('dd'); dt.textContent = title; dd.textContent = plain(value); list.append(dt, dd); }
  function showStatus(data) {
    latestSnapshot = {...latestSnapshot, ...data}; data = latestSnapshot;
    status = data.status || {};
    const sleep = status.sleep || {};
    const rows = [['Anzeige', sleep.active ? 'Schlafmodus' : status.active ? 'Uhr aktiv' : 'Playlist / bereit'], ['Schlafsteuerung', ({auto:'Automatik', sleep:'Schlafen', wake:'Wach'})[sleep.mode] || '—'], ['Ausnahme bis', sleep.until || 'Nächster Planwechsel'], ['Nächste Uhr (Sek.)', status.next_clock_seconds ?? '—'], ['Einträge verbleibend', status.entries_remaining ?? '—']];
    $('timeStageStatus').replaceChildren(...rows.map(([name, value]) => { const div = document.createElement('div'), label = document.createElement('small'), strong = document.createElement('strong'); label.textContent = name; strong.textContent = plain(value); div.append(label, strong); return div; }));
    $('timeStageRawStatus').textContent = JSON.stringify(status, null, 2);
    $('astronomyInfo').replaceChildren();
    const sky = data.astronomy || {};
    if (!Object.keys(sky).length) addDefinition($('astronomyInfo'), 'Himmelsdaten', null);
    const friendly = {sunrise:'Sonnenaufgang',sunset:'Sonnenuntergang',civil_dawn:'Bürgerliche Morgendämmerung',civil_dusk:'Ende der bürgerlichen Abenddämmerung',moonrise:'Mondaufgang',moonset:'Monduntergang',moon_phase:'Mondphase',moon_illumination:'Mondbeleuchtung',day_length_minutes:'Tageslänge',day_delta_minutes:'Änderung gegenüber gestern',moon_above_minutes:'Mond heute über dem Horizont',next_full_moon:'Nächster Vollmond',next_new_moon:'Nächster Neumond'};
    for (const [key,label] of Object.entries(friendly)) {
      let value=sky[key];
      if(value!=null && key.endsWith('_minutes')) value=`${Math.round(value)} min`;
      else if(value!=null && key==='moon_illumination') value=`${Number(value).toFixed(1)} %`;
      else if(typeof value==='string' && /^\d{4}-\d{2}-\d{2}T/.test(value)) value=new Date(value).toLocaleString('de-DE',{timeZone:original?.timezone});
      addDefinition($('astronomyInfo'),label,value);
    }
    if (data.location) addDefinition($('astronomyInfo'), 'Verwendeter Standort', data.location);
    $('astronomyRaw').textContent = JSON.stringify({astronomy:sky, location:data.location ?? null}, null, 2);
  }
  function minutes(time) { const [h, m] = time.split(':').map(Number); return h * 60 + m; }
  function timeText(value) { return `${String(Math.floor(value / 60)).padStart(2,'0')}:${String(value % 60).padStart(2,'0')}`; }
  function syncSleep(fromRange = false) {
    if (fromRange) { $('sleep_start').value = timeText(Number($('sleepStartRange').value)); $('sleep_end').value = timeText(Number($('sleepEndRange').value)); }
    const start = minutes($('sleep_start').value), end = minutes($('sleep_end').value);
    if (!Number.isFinite(start) || !Number.isFinite(end)) return;
    $('sleepStartRange').value = start; $('sleepEndRange').value = end;
    $('sleepStartRange').setAttribute('aria-valuetext', timeText(start)); $('sleepEndRange').setAttribute('aria-valuetext', timeText(end));
    const a = start / 1440 * 100, b = end / 1440 * 100, night = '#ed8250', day = '#29354d';
    $('sleepStrip').style.background = !$('sleep_enabled').checked || start === end ? day : start < end ? `linear-gradient(to right,${day} ${a}%,${night} ${a}%,${night} ${b}%,${day} ${b}%)` : `linear-gradient(to right,${night} ${b}%,${day} ${b}%,${day} ${a}%,${night} ${a}%)`;
    $('sleepPlan').textContent = !$('sleep_enabled').checked ? 'Täglicher Schlafplan deaktiviert.' : start === end ? 'Beginn und Ende sind gleich. Bitte zwei verschiedene Zeiten wählen.' : `Schlafzeit ${timeText(start)}–${timeText(end)}${start > end ? ' (über Mitternacht)' : ''}.`;
  }
  function syncLocation() { const custom = $('location_source').value === 'custom'; for (const id of ['latitude','longitude']) { $(id).disabled = !custom; $(id).required = custom; } }
  function normalScenes() { return catalog.filter(scene => !scene.events?.length); }
  function renderScenes() {
    const known = new Map(normalScenes().map(scene => [scene.key, scene]));
    $('sceneList').innerHTML = sceneOrder.filter(key => known.has(key)).map((key, i, keys) => {
      const scene = known.get(key);
      return `<article class="scene-row" data-scene-key="${escapeHtml(key)}"><div class="scene-title"><label class="check"><input type="checkbox" data-action="select" ${selected.has(key) ? 'checked' : ''}>${escapeHtml(scene.title)}</label></div><p class="muted">${escapeHtml(scene.description)}</p><p class="muted">Stil: ${escapeHtml(scene.style)} · Sekunden: ${escapeHtml(scene.seconds)}</p><div class="scene-controls"><label>Gewicht<input type="number" data-action="weight" min="1" max="10" step="1" value="${escapeHtml(weights[key] ?? 1)}" required></label><label class="check"><input type="checkbox" data-action="favorite" ${favorites.has(key) ? 'checked' : ''}>★ Favorit</label><button type="button" data-action="up" aria-label="${escapeHtml(scene.title)} nach oben" ${i === 0 ? 'disabled' : ''}>↑</button><button type="button" data-action="down" aria-label="${escapeHtml(scene.title)} nach unten" ${i === keys.length - 1 ? 'disabled' : ''}>↓</button></div></article>`;
    }).join('');
  }
  // Existing panel flags are always retained; only known, applicable controls are exposed.
  function panelOptions(category, panels) {
    const celestial = !['hour','half','quarter','midnight'].includes(category);
    if (!celestial) return [];
    const flags = {time:'Uhrzeit', next_event:'Nächstes Ereignis'};
    if (['moonrise','moonset','full_moon','new_moon'].includes(category)) Object.assign(flags, {phase:'Mondphase', illumination:'Mondbeleuchtung', next_full:'Nächster Vollmond', moon_above:'Mond über dem Horizont'});
    else Object.assign(flags, {day_length:'Tageslänge', day_delta:'Änderung der Tageslänge', twilight:'Dämmerung', night_length:'Nachtlänge'});
    // Discover additional flags provided by the backend without losing their values.
    if (object(panels)) for (const [key, value] of Object.entries(panels)) if (typeof value === 'boolean' && !(key in flags)) flags[key] = key;
    return Object.entries(flags);
  }
  function renderEvents() {
    $('eventList').innerHTML = Object.entries(categories).map(([category, title]) => {
      const event = original.events?.[category] || {}, choices = catalog.filter(scene => scene.events?.includes(category));
      const flags = panelOptions(category, event.panels);
       return `<details class="event-row" data-category="${category}"><summary>${title}${event.enabled ? ' · aktiv' : ''}</summary><label class="check"><input type="checkbox" data-event="enabled" ${event.enabled ? 'checked' : ''}>${title} aktivieren</label><label>Dauer (Sekunden)<input type="number" min="${['hour','half','quarter','midnight'].includes(category)?6:30}" max="60" step="1" data-event="duration" value="${escapeHtml(event.duration_seconds ?? 8)}" required></label><div class="event-scenes">${choices.length ? choices.map(scene => `<label class="check"><input type="checkbox" data-event="scene" value="${escapeHtml(scene.key)}" ${event.scenes?.includes(scene.key) ? 'checked' : ''}>${escapeHtml(categories[scene.key] || scene.title)}</label>`).join('') : '<p class="muted">Keine passende Szene im Katalog verfügbar.</p>'}</div>${flags.length ? `<p class="muted">Astronomische Anzeigefelder</p><div class="panel-flags">${flags.map(([key,label]) => `<label class="check"><input type="checkbox" data-panel="${escapeHtml(key)}" ${object(event.panels) ? event.panels[key] ? 'checked' : '' : Array.isArray(event.panels) && event.panels.includes(key) ? 'checked' : ''}>${escapeHtml(label)}</label>`).join('')}</div>` : ''}</details>`;
    }).join('');
  }
  function populate(data) {
    if (!object(data.config) || !Array.isArray(data.catalog)) throw new Error('Ungültige Antwort von GET /api/time-stage');
    original = clone(data.config); changedEvents.clear(); catalog = data.catalog.filter(scene => object(scene) && typeof scene.key === 'string');
    for (const id of scalarFields) $(id).value = original[id] ?? ({timezone:'Europe/Berlin', profile:'all', intensity:'normal', selection:'ordered'})[id];
    for (const id of numberFields) $(id).value = original[id] ?? ({after_entries:2, interval_seconds:50, duration_seconds:8, event_grace_seconds:120})[id];
    for (const id of checkFields) $(id).checked = !!original[id];
    $('color').value = original.color || '';
    const sleep = original.sleep || {};
    $('sleep_enabled').checked = !!sleep.enabled;
    $('sleep_start').value = sleep.start || '02:00'; $('sleep_end').value = sleep.end || '08:00';
    $('sleep_brightness').value = sleep.brightness ?? 1; $('sleep_color').value = sleep.color || '#ff500c';
    const loc = original.location || {};
    $('location_source').value = loc.source || 'weather'; $('latitude').value = loc.latitude ?? ''; $('longitude').value = loc.longitude ?? '';
    selected = new Set(original.scenes || []); favorites = new Set(original.favorites || []); weights = {...original.weights};
    sceneOrder = [...new Set([...(original.scenes || []), ...normalScenes().map(scene => scene.key)])];
    renderScenes(); renderEvents(); renderProfiles(); syncSleep();
    const previousScene = $('previewScene').value;
    $('previewScene').innerHTML = catalog.map(scene => `<option value="${escapeHtml(scene.key)}">${escapeHtml(categories[scene.key] || scene.title)}${scene.events?.length ? ' · Ereignis' : ' · Uhr'}</option>`).join('');
    if (catalog.some(scene => scene.key === previousScene)) $('previewScene').value = previousScene;
    showStatus(data); dirty = false; $('dirtyState').textContent = 'Keine ungespeicherten Änderungen.';
    $('timeStageFields').disabled = false; syncLocation();
    for (const id of ['previewScene','previewPlay','previewSnapshot','previewPhysical']) $(id).disabled = !catalog.length;
    $('exportTimeStage').disabled = false; $('importTimeStage').disabled = false;
  }
  function collect() {
    const config = clone(original);
    for (const id of scalarFields) config[id] = $(id).value.trim();
    for (const id of numberFields) config[id] = Number($(id).value);
    for (const id of checkFields) config[id] = $(id).checked;
    config.color = $('color').value.trim() || null;
    config.scenes = sceneOrder.filter(key => selected.has(key)); config.favorites = [...favorites]; config.weights = {...weights};
    config.sleep = {...config.sleep, enabled:$('sleep_enabled').checked, start:$('sleep_start').value, end:$('sleep_end').value, brightness:Number($('sleep_brightness').value), color:$('sleep_color').value};
    config.location = {...config.location, source:$('location_source').value};
    if (config.location.source === 'custom') { config.location.latitude = Number($('latitude').value); config.location.longitude = Number($('longitude').value); }
    config.events = {...config.events};
    document.querySelectorAll('[data-category]').forEach(row => {
      const category = row.dataset.category, old = config.events[category] || {}, available = [...row.querySelectorAll('[data-event="scene"]')];
      if (!Object.hasOwn(config.events, category) && !changedEvents.has(category)) return;
      const scenes = [...(old.scenes || []).filter(key => !available.some(node => node.value === key)), ...available.filter(node => node.checked).map(node => node.value)];
      const event = {...old, enabled:row.querySelector('[data-event="enabled"]').checked, duration_seconds:Number(row.querySelector('[data-event="duration"]').value), scenes};
      const controls = [...row.querySelectorAll('[data-panel]')];
      if (controls.length) {
        if (Array.isArray(old.panels)) event.panels = [...old.panels.filter(key => !controls.some(node => node.dataset.panel === key)), ...controls.filter(node => node.checked).map(node => node.dataset.panel)];
        else { event.panels = {...old.panels}; controls.forEach(node => { event.panels[node.dataset.panel] = node.checked; }); }
      }
      config.events[category] = event;
    });
    return config;
  }
  async function load() {
    if (busy || dirty && !confirm('Ungespeicherte Änderungen verwerfen und neu laden?')) return;
    busy = true; $('reloadTimeStage').disabled = true;
    try { populate(await api(base)); feedback('Einstellungen geladen.'); requestPreview(); }
    catch (error) { feedback(`GET ${base}: ${error.message}`, true); }
    finally { busy = false; $('reloadTimeStage').disabled = false; }
  }
  $('reloadTimeStage').onclick = load;
  $('timeStageForm').addEventListener('input', markDirty);
  $('timeStageForm').addEventListener('change', markDirty);
  $('eventList').addEventListener('change', event => { const row = event.target.closest('[data-category]'); if (row) changedEvents.add(row.dataset.category); });
  $('timeStageForm').addEventListener('invalid', event => {
    let parent = event.target.parentElement;
    while (parent) { if (parent.tagName === 'DETAILS') parent.open = true; parent = parent.parentElement; }
  }, true);
  $('timeStageForm').onsubmit = async event => {
    event.preventDefault(); if (busy || !original || !$('timeStageForm').reportValidity()) return;
    const config = collect();
    if (config.sleep.start === config.sleep.end) { feedback('Bitte unterschiedliche Schlafzeiten wählen.', true); return; }
    if (!config.scenes.length || config.profile === 'favorites' && !config.favorites.length) { feedback('Bitte mindestens eine Uhransicht auswählen (und für das Favoritenprofil einen Favoriten markieren).', true); return; }
    for (const [key, event] of Object.entries(config.events)) {
      if (!event.scenes.length || Array.isArray(event.panels) && !event.panels.length) { feedback(`Bitte mindestens eine Szene und ein Anzeigefeld für „${categories[key] || key}“ auswählen.`, true); return; }
    }
    busy = true; $('saveTimeStage').disabled = true; $('timeStageFields').disabled = true;
    try {
      const result = await api(base, {method:'PUT', body:JSON.stringify(config)});
      original = clone(result.config || config); dirty = false; $('dirtyState').textContent = 'Gespeichert.';
      if (result.status) showStatus(result);
      feedback('Time-Stage gespeichert.');
    } catch (error) { feedback(`PUT ${base}: ${error.message}`, true); }
    finally { busy = false; $('timeStageFields').disabled = false; $('saveTimeStage').disabled = false; syncLocation(); }
  };
  for (const id of ['sleep_start','sleep_end','sleep_enabled']) $(id).addEventListener('input', () => syncSleep());
  for (const id of ['sleepStartRange','sleepEndRange']) $(id).addEventListener('input', () => syncSleep(true));
  $('location_source').addEventListener('change', syncLocation);
  $('sceneList').addEventListener('input', event => {
    const row = event.target.closest('[data-scene-key]'); if (!row) return;
    const key = row.dataset.sceneKey, action = event.target.dataset.action;
    if (action === 'select') { event.target.checked ? selected.add(key) : selected.delete(key); $('profile').value = 'custom'; }
    if (action === 'favorite') event.target.checked ? favorites.add(key) : favorites.delete(key);
    if (action === 'weight') weights[key] = Number(event.target.value);
  });
  $('sceneList').addEventListener('click', event => {
    const button = event.target.closest('button[data-action]'), row = button?.closest('[data-scene-key]'); if (!row) return;
    const key = row.dataset.sceneKey, index = sceneOrder.indexOf(key), next = index + (button.dataset.action === 'up' ? -1 : 1);
    if (next < 0 || next >= sceneOrder.length) return;
    [sceneOrder[index], sceneOrder[next]] = [sceneOrder[next], sceneOrder[index]];
    markDirty(); renderScenes();
    const replacement = [...$('sceneList').querySelectorAll('[data-scene-key]')].find(node => node.dataset.sceneKey === key)?.querySelector(`[data-action="${button.dataset.action}"]`);
    if (replacement && !replacement.disabled) replacement.focus();
  });
  $('selectAllScenes').onclick = () => { normalScenes().forEach(scene => selected.add(scene.key)); $('profile').value = 'custom'; renderScenes(); markDirty(); };
  $('clearScenes').onclick = () => { selected.clear(); $('profile').value = 'custom'; renderScenes(); markDirty(); };
  document.querySelectorAll('[data-sleep-mode]').forEach(button => { button.onclick = async () => {
    if (busy) return;
    const payload = {mode:button.dataset.sleepMode}; if (button.dataset.minutes) payload.minutes = Number(button.dataset.minutes);
    busy = true; document.querySelectorAll('[data-sleep-mode]').forEach(node => { node.disabled = true; });
    try {
      const result = await api(`${base}/sleep`, {method:'POST', body:JSON.stringify(payload)});
      // Refresh status only: never replace unsaved form fields.
      const data = result.status ? result : await api(base);
      showStatus(data);
      if (original && data.config?.sleep) { original.sleep = {...original.sleep, mode:data.config.sleep.mode, until:data.config.sleep.until}; }
      else if (original) original.sleep = {...original.sleep, mode:payload.mode, until:data.status?.sleep?.until ?? null};
      feedback('Schlafsteuerung aktualisiert. Ungespeicherte Einstellungen bleiben erhalten.');
    } catch (error) { feedback(`POST ${base}/sleep: ${error.message}`, true); }
    finally { busy = false; document.querySelectorAll('[data-sleep-mode]').forEach(node => { node.disabled = false; }); }
  }; });
  function localDate(date) { const pad = n => String(n).padStart(2,'0'); return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`; }
  // Send a local datetime: the API interprets it in the configured Time-Stage
  // timezone, rather than silently shifting HH:MM to the browser's timezone.
  function position() { const delta = playing ? (performance.now() - motionAnchor) / 1000 * Number($('previewSpeed').value) : 0; return {at:localDate(new Date(clockAnchor + delta * 1000)), elapsed:Math.min(120, elapsedAnchor + delta)}; }
  function setAnchor() {
    const date = new Date($('previewAt').value);
    if (!Number.isFinite(date.getTime())) { $('previewFeedback').textContent = 'Bitte ein gültiges Datum mit Uhrzeit wählen.'; return false; }
    clockAnchor = date.getTime(); elapsedAnchor = Math.min(120, Math.max(0, Number($('previewElapsed').value) || 0)); motionAnchor = performance.now(); return true;
  }
  function invalidatePreview() { generation++; clearTimeout(timer); previewController?.abort(); }
  function setPlaying(value) {
    if (playing && !value) { const current = position(); clockAnchor = new Date(current.at).getTime(); elapsedAnchor = current.elapsed; }
    playing = value; motionAnchor = performance.now();
    $('previewPlay').textContent = playing ? 'Pausieren' : 'Abspielen'; $('previewPlay').setAttribute('aria-pressed', String(playing));
    if (!playing) { $('previewAt').value = localDate(new Date(clockAnchor)); $('previewElapsed').value = elapsedAnchor.toFixed(1); }
    invalidatePreview(); requestPreview();
  }
  function drawPixels(pixels) {
    if (!Array.isArray(pixels) || pixels.length !== 256) throw new Error('Vorschau enthält nicht 256 Pixel.');
    const packed = pixels.map(pixel => Array.isArray(pixel) ? ((pixel[0] & 255) << 16) | ((pixel[1] & 255) << 8) | (pixel[2] & 255) : typeof pixel === 'string' ? parseInt(pixel.replace(/^#/, ''),16) || 0 : Number(pixel) || 0);
    const signature = packed.join(','); if (signature === lastPixels) return;
    lastPixels = signature; matrix($('timeStageCanvas'), packed);
  }
  async function requestPreview() {
    clearTimeout(timer);
    if (previewBusy || document.hidden || !$('previewScene').value || !original) return;
    previewBusy = true; const version = generation, started = performance.now();
    previewController = new AbortController(); const timeout = setTimeout(() => previewController?.abort(), 8000);
    try {
      const current = position();
      const result = await api(`${base}/preview`, {method:'POST', body:JSON.stringify({key:$('previewScene').value, ...current, physical:false, confirm_wake:false}), signal:previewController.signal});
      if (version !== generation || document.hidden) return;
      drawPixels(result.pixels);
      $('previewFeedback').textContent = `${playing ? 'Läuft' : 'Schnappschuss'} · ${new Date(current.at).toLocaleString('de-DE')} (${original.timezone}) · ${Number($('previewSpeed').value)}× · nur Browser`;
    } catch (error) { if (version === generation && !document.hidden) $('previewFeedback').textContent = `POST ${base}/preview: ${error.message}`; }
    finally {
      clearTimeout(timeout); previewBusy = false; previewController = null;
      if (!document.hidden && (playing || version !== generation)) timer = setTimeout(requestPreview, Math.max(125, 250 - (performance.now() - started)));
    }
  }
  $('previewPlay').onclick = () => { if (!playing && !setAnchor()) return; setPlaying(!playing); };
  $('previewSnapshot').onclick = () => { if (!setAnchor()) return; setPlaying(false); };
  $('previewScene').onchange = () => { if (playing) clockAnchor = new Date(position().at).getTime(); elapsedAnchor = 0; $('previewElapsed').value = '0'; motionAnchor = performance.now(); invalidatePreview(); requestPreview(); };
  for (const id of ['previewAt','previewElapsed']) $(id).onchange = () => { if (setAnchor()) { invalidatePreview(); requestPreview(); } };
  $('previewTime').onchange = () => {
    if (!$('previewTime').value) return;
    const date = ($('previewAt').value || localDate(new Date())).slice(0,10);
    $('previewAt').value = `${date}T${$('previewTime').value}:00`;
    if (setAnchor()) setPlaying(false);
  };
  $('previewSpeed').addEventListener('focus', () => { if (playing) { const current = position(); clockAnchor = new Date(current.at).getTime(); elapsedAnchor = current.elapsed; motionAnchor = performance.now(); } });
  let oldSpeed = 1;
  $('previewSpeed').onchange = () => {
    if (playing) { const delta = (performance.now() - motionAnchor) / 1000 * oldSpeed; clockAnchor += delta * 1000; elapsedAnchor += delta; }
    oldSpeed = Number($('previewSpeed').value); motionAnchor = performance.now(); invalidatePreview(); requestPreview();
  };
  $('previewNow').onclick = () => { $('previewAt').value = localDate(new Date()); $('previewTime').value = $('previewAt').value.slice(11,16); $('previewElapsed').value = '0'; setAnchor(); invalidatePreview(); requestPreview(); };
  $('previewPhysical').onclick = async () => {
    if (busy || !$('previewScene').value) return;
    // Check the live status immediately before confirmation, not just the initial page state.
    busy = true; $('previewPhysical').disabled = true;
    try {
      const currentStatus = await api(base); showStatus(currentStatus);
      const sleeping = !!currentStatus.status?.sleep?.active;
      if (!confirm(sleeping ? 'Schlafmodus ist aktiv! Die LED-Vorschau kann die Anzeige aufwecken und heller leuchten lassen. Trotzdem auf den echten LEDs anzeigen?' : 'Diese Vorschau verändert die echte LED-Anzeige. Jetzt anzeigen?')) return;
      await api(`${base}/preview`, {method:'POST', body:JSON.stringify({key:$('previewScene').value, ...position(), physical:true, confirm_wake:sleeping})});
      $('previewFeedback').textContent = 'LED-Vorschau angefordert.';
    } catch (error) { $('previewFeedback').textContent = `POST ${base}/preview (LED): ${error.message}`; }
    finally { busy = false; $('previewPhysical').disabled = false; }
  };
  document.addEventListener('visibilitychange', () => { invalidatePreview(); if (!document.hidden) requestPreview(); });
  window.addEventListener('pagehide', () => { playing = false; invalidatePreview(); });
  window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
  $('exportTimeStage').onclick = async () => {
    $('exportTimeStage').disabled = true;
    try {
      const data = await api(`${base}/export`);
      if (!object(data) || !object(data.config)) throw new Error('Ungültiger Konfigurationsexport');
      // Export only the documented wrapper, never headers, tokens, or API diagnostics.
      const blob = new Blob([JSON.stringify({version:data.version ?? 1, config:data.config},null,2)], {type:'application/json'});
      const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = 'pixeldock-time-stage.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      feedback(dirty ? 'Gespeicherte Konfiguration exportiert; lokale Änderungen sind nicht enthalten.' : 'Konfiguration exportiert.');
    } catch (error) { feedback(`GET ${base}/export: ${error.message}`, true); }
    finally { $('exportTimeStage').disabled = false; }
  };
  function validateImport(data) {
    if (!object(data) || data.version !== 1 || !object(data.config)) throw new Error('Erwartet wird ein JSON-Objekt mit version: 1 und config.');
    const config = data.config;
    if (config.version !== undefined && config.version !== 1) throw new Error('Unbekannte Konfigurationsversion.');
    const rejectUnsafe = value => { if (!value || typeof value !== 'object') return; for (const [key, child] of Object.entries(value)) { if (['__proto__','prototype','constructor'].includes(key)) throw new Error('Unsicherer JSON-Schlüssel.'); rejectUnsafe(child); } };
    rejectUnsafe(data);
    for (const key of checkFields) if (typeof config[key] !== 'boolean') throw new Error(`Ungültiges Feld: ${key}`);
    const limits = {after_entries:[0,100], interval_seconds:[0,3600], duration_seconds:[1,300], event_grace_seconds:[0,3600]};
    for (const [key, [min,max]] of Object.entries(limits)) if (!Number.isInteger(config[key]) || config[key] < min || config[key] > max) throw new Error(`Ungültiges Zahlenfeld: ${key}`);
    const enums = {selection:['ordered','random'], profile:['all','retro','calm','favorites','custom'], intensity:['calm','normal','lively']};
    for (const [key, values] of Object.entries(enums)) if (!values.includes(config[key])) throw new Error(`Ungültige Auswahl: ${key}`);
    if (typeof config.timezone !== 'string' || !config.timezone) throw new Error('Zeitzone fehlt.');
    try { new Intl.DateTimeFormat('de-DE',{timeZone:config.timezone}); } catch (_) { throw new Error('Ungültige Zeitzone.'); }
    for (const key of ['scenes','favorites']) if (!Array.isArray(config[key]) || config[key].length > 64 || !config[key].every(value => typeof value === 'string') || new Set(config[key]).size !== config[key].length) throw new Error(`Ungültige Szenenliste: ${key}`);
    if (!config.scenes.length) throw new Error('Mindestens eine Uhransicht ist erforderlich.');
    if (!object(config.weights) || !Object.values(config.weights).every(value => Number.isInteger(value) && value >= 1 && value <= 10)) throw new Error('Ungültige Gewichte (1–10).');
    const hex = value => typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value);
    if (config.color != null && !hex(config.color)) throw new Error('Ungültige Farbe.');
    const sleep = config.sleep;
    if (!object(sleep) || typeof sleep.enabled !== 'boolean' || !['auto','sleep','wake'].includes(sleep.mode) || ![sleep.start,sleep.end].every(value => typeof value === 'string' && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value)) || !Number.isInteger(sleep.brightness) || sleep.brightness < 0 || sleep.brightness > 255 || !hex(sleep.color)) throw new Error('Ungültige Schlafkonfiguration.');
    if (sleep.start === sleep.end) throw new Error('Schlafbeginn und Schlafende müssen verschieden sein.');
    const loc = config.location;
    if (!object(loc) || !['weather','custom'].includes(loc.source)) throw new Error('Ungültige Standortquelle.');
    if (loc.source === 'custom' && !(typeof loc.latitude === 'number' && Number.isFinite(loc.latitude) && Math.abs(loc.latitude) <= 90 && typeof loc.longitude === 'number' && Number.isFinite(loc.longitude) && Math.abs(loc.longitude) <= 180)) throw new Error('Ungültige Koordinaten.');
    if (!object(config.events)) throw new Error('Ereigniskonfiguration fehlt.');
    for (const [key, event] of Object.entries(config.events)) {
      if (!object(event) || typeof event.enabled !== 'boolean' || !Array.isArray(event.scenes) || !event.scenes.length || event.scenes.length > 64 || !event.scenes.every(value => typeof value === 'string') || !Number.isInteger(event.duration_seconds) || event.duration_seconds < 6 || event.duration_seconds > 60) throw new Error(`Ungültiges Ereignis: ${key}`);
      if (event.panels != null && !(object(event.panels) || Array.isArray(event.panels))) throw new Error(`Ungültige Anzeigefelder: ${key}`);
    }
  }
  $('importTimeStage').onchange = async () => {
    const file = $('importTimeStage').files[0]; if (!file || busy) return;
    busy = true; $('importTimeStage').disabled = true;
    try {
      if (file.size > 128 * 1024) throw new Error('Die Datei ist größer als 128 KiB.');
      const text = await file.text(); let data;
      try { data = JSON.parse(text); } catch (_) { throw new Error('Die Datei enthält kein gültiges JSON.'); }
      validateImport(data);
      if (!confirm('Konfiguration auf dem Gerät importieren? Die gespeicherten Einstellungen und lokale Änderungen werden ersetzt.')) return;
      await api(`${base}/import`, {method:'POST', body:JSON.stringify(data)});
      dirty = false; populate(await api(base)); feedback('Konfiguration importiert.'); invalidatePreview(); requestPreview();
    } catch (error) { feedback(`Import ${base}/import: ${error.message}`, true); }
    finally { busy = false; $('importTimeStage').disabled = false; $('importTimeStage').value = ''; }
  };
  $('previewAt').value = localDate(new Date()); $('previewTime').value = $('previewAt').value.slice(11,16); setAnchor();
  function renderProfiles(){ $('savedProfile').innerHTML=Object.keys(original.profiles||{}).map(name=>`<option>${escapeHtml(name)}</option>`).join(''); }
  $('saveProfile').onclick=()=>{
    const name=$('profileName').value.trim();
    if(!name||['__proto__','constructor','prototype'].includes(name)){feedback('Bitte einen gültigen Profilnamen wählen.',true);return;}
    const profiles=original.profiles||{}, config=collect();
    if(!Object.hasOwn(profiles,name)&&Object.keys(profiles).length>=8){feedback('Maximal acht eigene Profile.',true);return;}
    original.profiles={...profiles,[name]:Object.fromEntries(['scenes','favorites','weights','selection','avoid_style_repeat','intensity','color'].map(key=>[key,config[key]]))};
    renderProfiles();$('savedProfile').value=name;markDirty();feedback('Profil vorgemerkt. Anschließend speichern.');
  };
  $('loadProfile').onclick=()=>{
    const profile=original.profiles?.[$('savedProfile').value];if(!profile)return;
    selected=new Set(profile.scenes);favorites=new Set(profile.favorites);weights={...profile.weights};
    sceneOrder=[...profile.scenes,...normalScenes().map(s=>s.key).filter(key=>!selected.has(key))];
    for(const key of ['selection','intensity'])$(key).value=profile[key];$('color').value=profile.color||'';$('avoid_style_repeat').checked=profile.avoid_style_repeat;$('profile').value='custom';
    renderScenes();markDirty();feedback('Profil geladen. Anschließend speichern.');
  };
  $('deleteProfile').onclick=()=>{const name=$('savedProfile').value;if(!name)return;delete original.profiles[name];renderProfiles();markDirty();};
  window.addEventListener('pixeldock-status',({detail})=>{if(original&&detail.display?.time_stage)showStatus({status:detail.display.time_stage});});
  setInterval(async()=>{if(document.hidden||!original||busy)return;try{const data=await api(base);showStatus({status:data.status,astronomy:data.astronomy,location:data.location});}catch(_){}},30000);
  load();
})();
