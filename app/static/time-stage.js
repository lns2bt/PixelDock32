/* Browser test hooks: timeStageForm, timeStageFields, saveTimeStage,
 * timeStageFeedback, dirtyState, sceneList [data-scene-key], eventList
 * [data-category], sleep_start/end, sleepStartRange/sleepEndRange, sleepStrip,
 * sleepNow/wakeNow/sleepAuto/sleepTwoHours, previewScene/At/Time/Elapsed/Speed,
 * previewPlay/Snapshot/Physical, timeStageCanvas, exportTimeStage/importTimeStage.
 * GET never writes; only dedicated LED preview buttons use physical:true.
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
    hour:'Full hour', half:'Half an hour', quarter:'Quarter of an hour', midnight:'Midnight',
    sunrise:'sunrise', sunset:'sunset', moonrise:'Moonrise', moonset:'Moonset',
    golden_hour:'Golden hour', solar_noon:'Peak of the sun', full_moon:'Full moon', new_moon:'New moon', equinox:'Equinox', solstice:'Solstice'
  };
  const skyLabels = { sunrise:'Sunrise', sunset:'Sunset', moonrise:'Moonrise', moonset:'Moonset', golden_hour:'Golden hour', solar_noon:'Peak of the sun', full_moon:'Full moon', new_moon:'New moon', equinox:'Equinox', solstice:'Solstice', moon_phase:'Moon phase', illumination:'Moon illumination', latitude:'Latitude', longitude:'Longitude', source:'Source', updated_at:'Calculated on', cached_at:'In the cache since', timezone:'Timezone' };
  const scalarFields = ['timezone','profile','intensity','selection','digit_transition'];
  const numberFields = ['after_entries','interval_seconds','duration_seconds','event_grace_seconds'];
  const checkFields = ['enabled','avoid_style_repeat','minute_transition'];
  let original = null, catalog = [], sceneOrder = [], selected = new Set(), favorites = new Set(), weights = {}, dirty = false, status = {}, busy = false;
  const changedEvents = new Set();
  let playing = false, timer = null, previewBusy = false, previewController = null, generation = 0;
  let clockAnchor = Date.now(), elapsedAnchor = 0, motionAnchor = performance.now();
  let lastPixels = '';
  let latestSnapshot = {};
  let revision = null;
  function feedback(text, error = false) { $('timeStageFeedback').textContent = text; $('timeStageFeedback').classList.toggle('error', error); }
  function markDirty() { dirty = true; $('dirtyState').textContent = 'Unsaved changes.'; }
  function plain(value) { return value == null ? 'Not available' : object(value) || Array.isArray(value) ? JSON.stringify(value) : String(value); }
  function addDefinition(list, title, value) { const dt = document.createElement('dt'), dd = document.createElement('dd'); dt.textContent = title; dd.textContent = plain(value); list.append(dt, dd); }
  function showStatus(data) {
    latestSnapshot = {...latestSnapshot, ...data}; data = latestSnapshot;
    status = data.status || {};
    const sleep = status.sleep || {};
    const zone = data.config?.timezone || status.timezone || original?.timezone || 'UTC';
    const deadline = sleep.until ? new Date(sleep.until).toLocaleString('en-GB', {timeZone:zone}) : '—';
    const rows = [['Display', sleep.active ? 'Sleep mode' : status.active ? 'Clock active' : 'Playlist / ready'], ['Sleep control', ({auto:'Automatic', sleep:'Sleep', wake:'Awake'})[sleep.mode] || '—'], [sleep.mode === 'auto' ? 'Next schedule change' : 'Override ends', deadline], ['Next clock in', status.next_clock_seconds == null ? '—' : `${Math.round(status.next_clock_seconds)} s`], ['Items until next clock', status.entries_remaining ?? '—']];
    $('timeStageStatus').replaceChildren(...rows.map(([name, value]) => { const div = document.createElement('div'), label = document.createElement('small'), strong = document.createElement('strong'); label.textContent = name; strong.textContent = plain(value); div.append(label, strong); return div; }));
    const next = sleep.mode !== 'auto' ? 'returns to automatic mode' : sleep.active ? 'wakes' : 'sleeps';
    $('sleepStatus').textContent = `${sleep.active ? 'Sleeping' : 'Awake'} · ${sleep.mode === 'auto' ? 'daily schedule' : 'temporary override'}${sleep.until ? ` · ${next}: ${deadline}` : ' · no scheduled change'} · ${zone}`;
    $('timeStageRawStatus').textContent = JSON.stringify(status, null, 2);
    $('astronomyInfo').replaceChildren();
    const sky = data.astronomy || {};
    if (!Object.keys(sky).length) addDefinition($('astronomyInfo'), 'Astronomy data', null);
    const friendly = {sunrise:'Sunrise',sunset:'Sunset',civil_dawn:'Civil dawn',civil_dusk:'End of civil twilight',moonrise:'Moonrise',moonset:'Moonset',moon_phase:'Moon phase',moon_illumination:'Moon illumination',day_length_minutes:'Day length',day_delta_minutes:'Change from yesterday',moon_above_minutes:'Moon above the horizon today',next_full_moon:'Next full moon',next_new_moon:'Next new moon'};
    for (const [key,label] of Object.entries(friendly)) {
      let value=sky[key];
      if(value!=null && key.endsWith('_minutes')) value=`${Math.round(value)} min`;
      else if(value!=null && key==='moon_illumination') value=`${Number(value).toFixed(1)} %`;
      else if(typeof value==='string' && /^\d{4}-\d{2}-\d{2}T/.test(value)) value=new Date(value).toLocaleString('en-GB',{timeZone:original?.timezone});
      addDefinition($('astronomyInfo'),label,value);
    }
    if (data.location) addDefinition($('astronomyInfo'), 'Location used', [data.location.latitude, data.location.longitude].every(Number.isFinite) ? `${Number(data.location.latitude).toFixed(4)}, ${Number(data.location.longitude).toFixed(4)} · ${data.location.source === 'custom' ? 'own coordinates' : 'weather location'}` : data.location.source || '—');
    $('astronomyRaw').textContent = JSON.stringify({astronomy:sky, location:data.location ?? null}, null, 2);
  }
  function minutes(time) { const [h, m] = time.split(':').map(Number); return h * 60 + m; }
  function timeText(value) { return `${String(Math.floor(value / 60)).padStart(2,'0')}:${String(value % 60).padStart(2,'0')}`; }
  function syncSleep(rangeId = null) {
    if (rangeId === 'sleepStartRange') $('sleep_start').value = timeText(Number($('sleepStartRange').value));
    if (rangeId === 'sleepEndRange') $('sleep_end').value = timeText(Number($('sleepEndRange').value));
    const start = minutes($('sleep_start').value), end = minutes($('sleep_end').value);
    if (!Number.isFinite(start) || !Number.isFinite(end)) return;
    $('sleepStartRange').value = start; $('sleepEndRange').value = end;
    $('sleepStartRange').setAttribute('aria-valuetext', timeText(start)); $('sleepEndRange').setAttribute('aria-valuetext', timeText(end));
    $('sleepStartValue').textContent = timeText(start); $('sleepEndValue').textContent = timeText(end);
    const a = start / 1440 * 100, b = end / 1440 * 100, night = '#ed8250', day = '#29354d';
    $('sleepStrip').style.background = !$('sleep_enabled').checked || start === end ? day : start < end ? `linear-gradient(to right,${day} ${a}%,${night} ${a}%,${night} ${b}%,${day} ${b}%)` : `linear-gradient(to right,${night} ${b}%,${day} ${b}%,${day} ${a}%,${night} ${a}%)`;
    const duration = (end - start + 1440) % 1440;
    $('sleepPlan').textContent = !$('sleep_enabled').checked ? 'Daily sleep schedule disabled.' : start === end ? 'Choose two different times.' : `Sleep ${timeText(start)}–${timeText(end)}${start > end ? ' (overnight)' : ''} · ${Math.floor(duration / 60)} h ${duration % 60} min · ${$('timezone').value}${duration > 720 ? ' · Warning: more than 12 hours of sleep per day.' : ''}`;
  }
  function syncLocation() { const custom = $('location_source').value === 'custom'; for (const id of ['latitude','longitude']) { $(id).disabled = !custom; $(id).required = custom; } }
  function normalScenes() { return catalog.filter(scene => !scene.events?.length); }
  function renderScenes() {
    const known = new Map(normalScenes().map(scene => [scene.key, scene]));
    $('sceneList').innerHTML = sceneOrder.filter(key => known.has(key)).map((key, i, keys) => {
      const scene = known.get(key);
      const isNew = !!scene.added && !(original?.scenes || []).includes(key);
      return `<article class="scene-row" data-scene-key="${escapeHtml(key)}"><div class="scene-title"><label class="check"><input type="checkbox" data-action="select" ${selected.has(key) ? 'checked' : ''}>${escapeHtml(scene.title)}</label>${isNew ? '<span class="chip new">New</span>' : ''}</div><p class="muted">${escapeHtml(scene.description)}</p><p class="muted">Style: ${escapeHtml(scene.style)} · Seconds: ${escapeHtml(scene.seconds)}</p><div class="scene-controls"><label>Weight<input type="number" data-action="weight" min="1" max="10" step="1" value="${escapeHtml(weights[key] ?? 1)}" required></label><label class="check"><input type="checkbox" data-action="favorite" ${favorites.has(key) ? 'checked' : ''}>★ Favourite</label><button type="button" data-action="up" aria-label="${escapeHtml(scene.title)} up" ${i === 0 ? 'disabled' : ''}>↑</button><button type="button" data-action="down" aria-label="${escapeHtml(scene.title)} downward" ${i === keys.length - 1 ? 'disabled' : ''}>↓</button><button type="button" data-preview-key="${escapeHtml(key)}" aria-label="${escapeHtml(scene.title)}: show on LEDs">On LEDs</button></div></article>`;
    }).join('');
    const missing = normalScenes().filter(scene => scene.added && !selected.has(scene.key) && !(original?.scenes || []).includes(scene.key));
    $('addNewScenes').hidden = !missing.length;
    $('addNewScenes').textContent = `+ Add ${missing.length} new view${missing.length === 1 ? '' : 's'}`;
  }
  // Existing panel flags are always retained; only known, applicable controls are exposed.
  function panelOptions(category, panels) {
    const celestial = !['hour','half','quarter','midnight'].includes(category);
    if (!celestial) return [];
    const flags = {time:'Time', next_event:'Next event'};
    if (['moonrise','moonset','full_moon','new_moon'].includes(category)) Object.assign(flags, {phase:'Moon phase', illumination:'Moon illumination', next_full:'Next full moon', moon_above:'Moon over the horizon'});
    else Object.assign(flags, {day_length:'Day length', day_delta:'Change in day length', twilight:'Twilight', night_length:'Night length'});
    // Discover additional flags provided by the backend without losing their values.
    if (object(panels)) for (const [key, value] of Object.entries(panels)) if (typeof value === 'boolean' && !(key in flags)) flags[key] = key;
    return Object.entries(flags);
  }
  function renderEvents() {
    $('eventList').innerHTML = Object.entries(categories).map(([category, title]) => {
      const event = original.events?.[category] || {}, choices = catalog.filter(scene => scene.events?.includes(category));
      const flags = panelOptions(category, event.panels);
       return `<details class="event-row" data-category="${category}"><summary>${title}${event.enabled ? ' · active' : ''}</summary><label class="check"><input type="checkbox" data-event="enabled" ${event.enabled ? 'checked' : ''}>Enable ${title.toLowerCase()}</label><label>Duration (seconds)<input type="number" min="${['hour','half','quarter','midnight'].includes(category)?6:30}" max="60" step="1" data-event="duration" value="${escapeHtml(event.duration_seconds ?? 8)}" required></label><div class="event-scenes">${choices.length ? choices.map(scene => `<div class="event-scene-preview"><label class="check"><input type="checkbox" data-event="scene" value="${escapeHtml(scene.key)}" ${event.scenes?.includes(scene.key) ? 'checked' : ''}>${escapeHtml(categories[scene.key] || scene.title)}</label><button type="button" data-preview-key="${escapeHtml(scene.key)}" aria-label="${escapeHtml(categories[scene.key] || scene.title)}: LED preview">LED preview</button></div>`).join('') : '<p class="muted">No matching scene available in the catalog.</p>'}</div>${flags.length ? `<p class="muted">Astronomical display panels</p><div class="panel-flags">${flags.map(([key,label]) => `<label class="check"><input type="checkbox" data-panel="${escapeHtml(key)}" ${object(event.panels) ? event.panels[key] ? 'checked' : '' : Array.isArray(event.panels) && event.panels.includes(key) ? 'checked' : ''}>${escapeHtml(label)}</label>`).join('')}</div>` : ''}</details>`;
    }).join('');
  }
  function populate(data) {
    if (!object(data.config) || !Array.isArray(data.catalog)) throw new Error('Invalid response from GET /api/time-stage');
    revision = data.revision;
    original = clone(data.config); changedEvents.clear(); catalog = data.catalog.filter(scene => object(scene) && typeof scene.key === 'string');
    for (const id of scalarFields) $(id).value = original[id] ?? ({timezone:'Europe/Vienna', profile:'all', intensity:'normal', selection:'ordered', digit_transition:'auto'})[id];
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
    $('previewScene').innerHTML = catalog.map(scene => `<option value="${escapeHtml(scene.key)}">${escapeHtml(categories[scene.key] || scene.title)}${scene.events?.length ? ' · Event' : ' · Clock'}</option>`).join('');
    if (catalog.some(scene => scene.key === previousScene)) $('previewScene').value = previousScene;
    showStatus(data); dirty = false; $('dirtyState').textContent = 'No unsaved changes.';
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
  function validatedConfig() {
    if (!$('timeStageForm').checkValidity()) throw new Error('Please correct the invalid settings.');
    const config = collect();
    if (config.sleep.start === config.sleep.end) throw new Error('Please choose different sleeping times.');
    if (!config.scenes.length || config.profile === 'favorites' && !config.favorites.length) throw new Error('Please select at least one clock view (and mark a favorite for the favorite profile).');
    for (const [key, event] of Object.entries(config.events)) {
      if (!event.scenes.length || Array.isArray(event.panels) && !event.panels.length) throw new Error(`Please at least one scene and one display field for “${categories[key] || key}" choose.`);
    }
    return config;
  }
  async function load() {
    if (busy || dirty && !confirm('Discard unsaved changes and reload?')) return;
    busy = true; $('reloadTimeStage').disabled = true;
    try { populate(await api(base)); feedback('Settings loaded.'); requestPreview(); }
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
    let config;
    try { config = validatedConfig(); } catch (error) { feedback(error.message, true); return; }
    const duration = (minutes(config.sleep.end) - minutes(config.sleep.start) + 1440) % 1440;
    if (config.sleep.enabled && duration > 720 && !confirm(`Sleep ${config.sleep.start}–${config.sleep.end}: ${Math.floor(duration/60)} h ${duration%60} min per day. Save this long sleep period?`)) return;
    busy = true; $('saveTimeStage').disabled = true; $('timeStageFields').disabled = true;
    try {
      const result = await api(base, {method:'PUT', headers:revision ? {'If-Match':revision} : {}, body:JSON.stringify(config)});
      const verified = await api(base);
      if (!result.config || !verified.config || ['start','end','enabled'].some(key => result.config.sleep[key] !== config.sleep[key] || verified.config.sleep[key] !== config.sleep[key]) || verified.config.timezone !== config.timezone) {
        throw new Error('Saved sleep times differ from your selection. Reload and check the schedule.');
      }
      populate(verified);
      $('dirtyState').textContent = 'Saved and verified.';
      feedback(`Time-Stage saved. Confirmed sleep: ${verified.config.sleep.start}–${verified.config.sleep.end} · ${verified.config.timezone}.`);
    } catch (error) { feedback(`PUT ${base}: ${error.message}`, true); }
    finally { busy = false; $('timeStageFields').disabled = false; $('saveTimeStage').disabled = false; syncLocation(); }
  };
  for (const id of ['sleep_start','sleep_end','sleep_enabled']) $(id).addEventListener('input', () => syncSleep());
  for (const id of ['sleepStartRange','sleepEndRange']) $(id).addEventListener('input', () => syncSleep(id));
  $('location_source').addEventListener('change', syncLocation);
  // Tabs: one topic at a time; the save bar stays visible on every tab.
  const tabNames = [...document.querySelectorAll('[data-tab-target]')].map(button => button.dataset.tabTarget);
  function showTab(name) {
    if (!tabNames.includes(name)) name = tabNames[0];
    document.querySelectorAll('[data-tab]').forEach(node => { node.hidden = node.dataset.tab !== name; });
    document.querySelectorAll('[data-tab-target]').forEach(button => button.setAttribute('aria-selected', String(button.dataset.tabTarget === name)));
    try { history.replaceState(null, '', '#' + name); } catch (_) {}
  }
  document.querySelectorAll('[data-tab-target]').forEach(button => button.addEventListener('click', () => showTab(button.dataset.tabTarget)));
  // An invalid field on a hidden tab would block saving silently: reveal it.
  $('timeStageForm').addEventListener('invalid', event => { const tab = event.target.closest('[data-tab]'); if (tab?.hidden) showTab(tab.dataset.tab); }, true);
  showTab(location.hash.slice(1));
  $('addNewScenes').addEventListener('click', () => {
    for (const scene of normalScenes()) if (scene.added && !(original?.scenes || []).includes(scene.key)) selected.add(scene.key);
    markDirty(); renderScenes(); feedback('New clock views selected. Save to add them to the rotation.');
  });
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
      feedback('Sleep controls updated. Unsaved settings are retained.');
    } catch (error) { feedback(`POST ${base}/sleep: ${error.message}`, true); }
    finally { busy = false; document.querySelectorAll('[data-sleep-mode]').forEach(node => { node.disabled = false; }); }
  }; });
  function localDate(date) { const pad = n => String(n).padStart(2,'0'); return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`; }
  // Send a local datetime: the API interprets it in the configured Time-Stage
  // timezone, rather than silently shifting HH:MM to the browser's timezone.
  function position() { const delta = playing ? (performance.now() - motionAnchor) / 1000 * Number($('previewSpeed').value) : 0; return {at:localDate(new Date(clockAnchor + delta * 1000)), elapsed:Math.min(120, elapsedAnchor + delta)}; }
  function setAnchor() {
    const date = new Date($('previewAt').value);
    if (!Number.isFinite(date.getTime())) { $('previewFeedback').textContent = 'Please select a valid date and time.'; return false; }
    clockAnchor = date.getTime(); elapsedAnchor = Math.min(120, Math.max(0, Number($('previewElapsed').value) || 0)); motionAnchor = performance.now(); return true;
  }
  function invalidatePreview() { generation++; clearTimeout(timer); previewController?.abort(); }
  function setPlaying(value) {
    if (playing && !value) { const current = position(); clockAnchor = new Date(current.at).getTime(); elapsedAnchor = current.elapsed; }
    playing = value; motionAnchor = performance.now();
    $('previewPlay').textContent = playing ? 'Pause browser preview' : 'Play browser preview'; $('previewPlay').setAttribute('aria-pressed', String(playing));
    if (!playing) { $('previewAt').value = localDate(new Date(clockAnchor)); $('previewElapsed').value = elapsedAnchor.toFixed(1); }
    invalidatePreview(); requestPreview();
  }
  function drawPixels(pixels) {
    if (!Array.isArray(pixels) || pixels.length !== 256) throw new Error('Preview does not contain 256 pixels.');
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
      const settings = validatedConfig();
      const result = await api(`${base}/preview`, {method:'POST', body:JSON.stringify({key:$('previewScene').value, settings, ...current, physical:false, confirm_wake:false}), signal:previewController.signal});
      if (version !== generation || document.hidden) return;
      drawPixels(result.pixels);
      $('previewFeedback').textContent = `Browser preview · ${playing ? 'Running' : 'Snapshot'} · ${new Date(current.at).toLocaleString('en-GB')} (${settings.timezone}) · ${Number($('previewSpeed').value)}×`;
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
  async function physicalPreview(key) {
    if (busy || !original || !key) return;
    if (!$('timeStageForm').reportValidity()) return;
    busy = true;
    const buttons = [...document.querySelectorAll('[data-preview-key], #previewPhysical')];
    buttons.forEach(button => { button.disabled = true; });
    try {
      await api(`${base}/preview`, {method:'POST', body:JSON.stringify({key, settings:validatedConfig(), physical:true, confirm_wake:false})});
      $('previewFeedback').textContent = 'LED preview requested.';
      feedback('LED preview started. The playlist then continues.');
    } catch (error) { $('previewFeedback').textContent = `LED preview: ${error.message}`; feedback(`LED preview: ${error.message}`, true); }
    finally { busy = false; buttons.forEach(button => { button.disabled = false; }); }
  }
  $('previewPhysical').onclick = () => physicalPreview($('previewScene').value);
  for (const id of ['sceneList','eventList']) $(id).addEventListener('click', event => {
    const button = event.target.closest('button[data-preview-key]');
    if (button) physicalPreview(button.dataset.previewKey);
  });
  document.addEventListener('visibilitychange', () => { invalidatePreview(); if (!document.hidden) requestPreview(); });
  window.addEventListener('pagehide', () => { playing = false; invalidatePreview(); });
  window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
  $('exportTimeStage').onclick = async () => {
    $('exportTimeStage').disabled = true;
    try {
      const data = await api(`${base}/export`);
      if (!object(data) || !object(data.config)) throw new Error('Invalid configuration export');
      // Export only the documented wrapper, never headers, tokens, or API diagnostics.
      const blob = new Blob([JSON.stringify({version:data.version ?? 1, config:data.config},null,2)], {type:'application/json'});
      const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = 'pixeldock-time-stage.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      feedback(dirty ? 'Saved configuration exported; local changes are not included.' : 'Configuration exported.');
    } catch (error) { feedback(`GET ${base}/export: ${error.message}`, true); }
    finally { $('exportTimeStage').disabled = false; }
  };
  function validateImport(data) {
    if (!object(data) || data.version !== 1 || !object(data.config)) throw new Error('A JSON object with version: 1 and config is expected.');
    const config = data.config;
    if (config.version !== undefined && config.version !== 1) throw new Error('Unknown configuration version.');
    const rejectUnsafe = value => { if (!value || typeof value !== 'object') return; for (const [key, child] of Object.entries(value)) { if (['__proto__','prototype','constructor'].includes(key)) throw new Error('Insecure JSON key.'); rejectUnsafe(child); } };
    rejectUnsafe(data);
    for (const key of checkFields) if (typeof config[key] !== 'boolean') throw new Error(`Invalid field: ${key}`);
    const limits = {after_entries:[0,100], interval_seconds:[0,3600], duration_seconds:[1,300], event_grace_seconds:[0,3600]};
    for (const [key, [min,max]] of Object.entries(limits)) if (!Number.isInteger(config[key]) || config[key] < min || config[key] > max) throw new Error(`Invalid number field: ${key}`);
    const enums = {selection:['ordered','random'], profile:['all','retro','calm','favorites','custom'], intensity:['calm','normal','lively']};
    for (const [key, values] of Object.entries(enums)) if (!values.includes(config[key])) throw new Error(`Invalid selection: ${key}`);
    if (typeof config.timezone !== 'string' || !config.timezone) throw new Error('Time zone is missing.');
    try { new Intl.DateTimeFormat('en-GB',{timeZone:config.timezone}); } catch (_) { throw new Error('Invalid time zone.'); }
    for (const key of ['scenes','favorites']) if (!Array.isArray(config[key]) || config[key].length > 64 || !config[key].every(value => typeof value === 'string') || new Set(config[key]).size !== config[key].length) throw new Error(`Invalid scene list: ${key}`);
    if (!config.scenes.length) throw new Error('At least one clock view is required.');
    if (!object(config.weights) || !Object.values(config.weights).every(value => Number.isInteger(value) && value >= 1 && value <= 10)) throw new Error('Invalid weights (1-10).');
    const hex = value => typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value);
    if (config.color != null && !hex(config.color)) throw new Error('Invalid color.');
    const sleep = config.sleep;
    if (!object(sleep) || typeof sleep.enabled !== 'boolean' || !['auto','sleep','wake'].includes(sleep.mode) || ![sleep.start,sleep.end].every(value => typeof value === 'string' && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value)) || !Number.isInteger(sleep.brightness) || sleep.brightness < 0 || sleep.brightness > 255 || !hex(sleep.color)) throw new Error('Invalid sleep configuration.');
    if (sleep.start === sleep.end) throw new Error('The beginning and end of sleep must be different.');
    const loc = config.location;
    if (!object(loc) || !['weather','custom'].includes(loc.source)) throw new Error('Invalid location source.');
    if (loc.source === 'custom' && !(typeof loc.latitude === 'number' && Number.isFinite(loc.latitude) && Math.abs(loc.latitude) <= 90 && typeof loc.longitude === 'number' && Number.isFinite(loc.longitude) && Math.abs(loc.longitude) <= 180)) throw new Error('Invalid coordinates.');
    if (!object(config.events)) throw new Error('Event configuration is missing.');
    for (const [key, event] of Object.entries(config.events)) {
      if (!object(event) || typeof event.enabled !== 'boolean' || !Array.isArray(event.scenes) || !event.scenes.length || event.scenes.length > 64 || !event.scenes.every(value => typeof value === 'string') || !Number.isInteger(event.duration_seconds) || event.duration_seconds < 6 || event.duration_seconds > 60) throw new Error(`Invalid event: ${key}`);
      if (event.panels != null && !(object(event.panels) || Array.isArray(event.panels))) throw new Error(`Invalid display fields: ${key}`);
    }
  }
  $('importTimeStage').onchange = async () => {
    const file = $('importTimeStage').files[0]; if (!file || busy) return;
    busy = true; $('importTimeStage').disabled = true;
    try {
      if (file.size > 128 * 1024) throw new Error('The file is larger than 128 KiB.');
      const text = await file.text(); let data;
      try { data = JSON.parse(text); } catch (_) { throw new Error('The file does not contain valid JSON.'); }
      validateImport(data);
      if (!confirm('Import configuration to the device? The saved settings and local changes are replaced.')) return;
      await api(`${base}/import`, {method:'POST', body:JSON.stringify(data)});
      dirty = false; populate(await api(base)); feedback('Configuration imported.'); invalidatePreview(); requestPreview();
    } catch (error) { feedback(`Import ${base}/import: ${error.message}`, true); }
    finally { busy = false; $('importTimeStage').disabled = false; $('importTimeStage').value = ''; }
  };
  $('previewAt').value = localDate(new Date()); $('previewTime').value = $('previewAt').value.slice(11,16); setAnchor();
  function renderProfiles(){ $('savedProfile').innerHTML=Object.keys(original.profiles||{}).map(name=>`<option>${escapeHtml(name)}</option>`).join(''); }
  $('saveProfile').onclick=()=>{
    const name=$('profileName').value.trim();
    if(!name||['__proto__','constructor','prototype'].includes(name)){feedback('Please choose a valid profile name.',true);return;}
    const profiles=original.profiles||{}, config=collect();
    if(!Object.hasOwn(profiles,name)&&Object.keys(profiles).length>=8){feedback('A maximum of eight personal profiles.',true);return;}
    original.profiles={...profiles,[name]:Object.fromEntries(['scenes','favorites','weights','selection','avoid_style_repeat','intensity','color'].map(key=>[key,config[key]]))};
    renderProfiles();$('savedProfile').value=name;markDirty();feedback('Profile noted. Then save.');
  };
  $('loadProfile').onclick=()=>{
    const profile=original.profiles?.[$('savedProfile').value];if(!profile)return;
    selected=new Set(profile.scenes);favorites=new Set(profile.favorites);weights={...profile.weights};
    sceneOrder=[...profile.scenes,...normalScenes().map(s=>s.key).filter(key=>!selected.has(key))];
    for(const key of ['selection','intensity'])$(key).value=profile[key];$('color').value=profile.color||'';$('avoid_style_repeat').checked=profile.avoid_style_repeat;$('profile').value='custom';
    renderScenes();markDirty();feedback('Profile loaded. Then save.');
  };
  $('deleteProfile').onclick=()=>{const name=$('savedProfile').value;if(!name)return;delete original.profiles[name];renderProfiles();markDirty();};
  window.addEventListener('pixeldock-status',({detail})=>{if(original&&detail.display?.time_stage)showStatus({status:detail.display.time_stage});});
  setInterval(async()=>{if(document.hidden||!original||busy)return;try{const data=await api(base);showStatus({status:data.status,astronomy:data.astronomy,location:data.location});}catch(_){}},30000);
  load();
})();
