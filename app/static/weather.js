/* Browser demo controls never enter physical preview payloads. No preview writes settings. */
(() => {
  'use strict';
  if (!window.PixelDock) return;
  const {api, matrix, toast} = window.PixelDock, $ = id => document.getElementById(id);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fields = ['weather_stage','weather_max_infos','weather_read_seconds','weather_info_order','weather_style_order','weather_intensity','weather_comfort_min','weather_comfort_max'];
  const defaults = {weather_stage:true,weather_max_infos:2,weather_read_seconds:4,weather_info_order:'ordered',weather_style_order:'ordered',weather_intensity:'normal',weather_comfort_min:19,weather_comfort_max:25};
  let catalog, rows = [], row, settings, infoOrder = [], styleOrder = [], baseline, dirty = false;
  let playing = false, browserBusy = false, pendingFrame = false, timer, revision = 0, anchor = 0, start = 0;
  let previewQueue = Promise.resolve(), lastRequest = -Infinity;
  let physicalRevision = 0;
  let durationTimer, durationBusy = false, durationPending = false, durationRevision = 0;
  const ordered = (selected, entries) => [...new Set([...(Array.isArray(selected) ? selected : []), ...entries.map(entry => entry.key)])].filter(key => entries.some(entry => entry.key === key));
  const title = entry => entry.title || entry.label || entry.name || entry.key;
  const classic = {outside:'show_outdoor',inside:'show_indoor',humidity:'show_humidity'};
  function message(text, error = false) { $('weatherFeedback').textContent = text; $('weatherFeedback').style.color = error ? '#ff9080' : ''; }
  function checked(kind, key) { return [...$(`weather${kind}`).querySelectorAll('input[type=checkbox]')].find(node => node.value === key)?.checked; }
  function collect() {
    const result = {...settings};
    for (const key of fields) { const node = $(key); result[key] = node.type === 'checkbox' ? node.checked : node.type === 'number' ? Number(node.value) : node.value; }
    result.weather_infos = infoOrder.filter(key => checked('Infos', key));
    result.weather_styles = styleOrder.filter(key => checked('Styles', key));
    for (const [key, flag] of Object.entries(classic)) if (catalog.infos.some(entry => entry.key === key)) result[flag] = result.weather_infos.includes(key);
    return result;
  }
  function summaries(s) {
    $('weatherInfosSummary').textContent = `${s.weather_infos.length} ausgewählt · max. ${s.weather_max_infos}`;
    $('weatherStylesSummary').textContent = `${s.weather_styles.length} von ${catalog.styles.length} ausgewählt`;
  }
  function mark() {
    if (!row) return;
    const s = collect(); dirty = JSON.stringify(s) !== baseline;
    $('weatherSavebar').hidden = !dirty; $('weatherDirty').textContent = dirty ? 'Ungespeichert' : '';
    summaries(s); scheduleDuration(); revision++; clearFrame();
    if (playing) requestFrame();
  }
  function scheduleDuration() {
    durationRevision++; durationPending = false; clearTimeout(durationTimer);
    if (!row) return;
    $('weatherDuration').textContent = 'Dauer wird berechnet …';
    durationTimer = setTimeout(() => { durationPending = true; updateDuration(); }, 200);
  }
  async function updateDuration() {
    if (durationBusy || !durationPending || !row) return;
    durationBusy = true; durationPending = false;
    const currentRevision = durationRevision, moduleId = row.id;
    try {
      const data = await api('/api/weather/duration', {method:'POST',body:JSON.stringify({module_id:moduleId,settings:collect()})});
      if (currentRevision === durationRevision && row.id === moduleId) {
        const seconds = Number(data.duration ?? data.duration_seconds);
        $('weatherDuration').textContent = data.automatic
          ? `Automatisch · ca. ${Number.isFinite(seconds) ? seconds.toLocaleString('de-DE',{maximumFractionDigits:1}) : '—'} s · ${data.info_count} Infos · ${data.read_seconds} s Lesezeit.`
          : `Klassisch · ${row.duration_seconds} s · Dauer in der Playlist editierbar.`;
      }
    } catch (error) { if (currentRevision === durationRevision) $('weatherDuration').textContent = `Dauer nicht verfügbar: ${error.message}`; }
    finally { durationBusy = false; if (durationPending) updateDuration(); }
  }
  function renderChoices(kind, order, selected) {
    const entries = kind === 'Infos' ? catalog.infos : catalog.styles;
    $(`weather${kind}`).innerHTML = order.map((key, i) => {
      const entry = entries.find(value => value.key === key), label = escape(title(entry));
      return `<div class="weather-row" data-${kind === 'Infos' ? 'info' : 'style-row'}="${escape(key)}"><div class="row-top"><label class="check"><input type="checkbox" value="${escape(key)}" ${selected.includes(key) ? 'checked' : ''}>${label}</label><button type="button" data-move="-1" aria-label="${label} nach oben" ${i === 0 ? 'disabled' : ''}>↑</button><button type="button" data-move="1" aria-label="${label} nach unten" ${i === order.length - 1 ? 'disabled' : ''}>↓</button>${kind === 'Styles' ? `<button type="button" data-led-style="${escape(key)}" aria-label="${label} auf LEDs zeigen">LED-Vorschau</button><button type="button" data-style="${escape(key)}" aria-label="${label} im Browser zeigen">Browser</button>` : ''}</div>${entry.description ? `<details class="weather-description"><summary>Beschreibung</summary><p class="muted">${escape(entry.description)}</p></details>` : ''}</div>`;
    }).join('');
    $(`weather${kind}`).querySelectorAll('[data-move]').forEach(button => button.onclick = () => {
      settings = collect(); const parent = button.closest('.weather-row'), index = order.indexOf(parent.dataset.info ?? parent.dataset.styleRow), target = index + Number(button.dataset.move);
      [order[index], order[target]] = [order[target], order[index]];
      renderChoices(kind, order, kind === 'Infos' ? settings.weather_infos : settings.weather_styles); mark();
    });
    $('weatherStyles').querySelectorAll('[data-style]').forEach(button => button.onclick = () => {
      stop(); revision++; clearFrame(); $('weatherPreviewStyle').value = button.dataset.style; $('weatherElapsed').value = 0; $('weatherBrowserPreview').open = true;
      requestFrame(); $('weatherCanvas').scrollIntoView({block:'center'});
    });
    $('weatherStyles').querySelectorAll('[data-led-style]').forEach(button => button.onclick = () => physicalPreview(button.dataset.ledStyle, null, $('weatherLedStatus'), button));
  }
  function fill(selected) {
    stop(); revision++; clearFrame(); row = selected;
    settings = {...defaults,...catalog.defaults,...row.settings};
    if (!Array.isArray(row.settings?.weather_infos)) settings.weather_infos = catalog.infos.filter(entry => !classic[entry.key] || settings[classic[entry.key]] !== false).map(entry => entry.key);
    if (!Array.isArray(settings.weather_styles)) settings.weather_styles = catalog.styles.map(entry => entry.key);
    infoOrder = ordered(settings.weather_infos,catalog.infos); styleOrder = ordered(settings.weather_styles,catalog.styles);
    for (const key of fields) { const node = $(key); if (node.type === 'checkbox') node.checked = settings[key]; else node.value = settings[key]; }
    renderChoices('Infos',infoOrder,settings.weather_infos); renderChoices('Styles',styleOrder,settings.weather_styles);
    baseline = JSON.stringify(collect()); dirty = false; $('weatherSavebar').hidden = true; $('weatherDirty').textContent = ''; $('weatherFields').disabled = false;
    for (const id of ['weatherPreviewPlay','weatherSnapshot','weatherPhysical']) $(id).disabled = false;
    $('weatherLedStatus').textContent = ''; summaries(collect()); scheduleDuration(); message('Wetter geladen.');
  }
  const display = value => value == null ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value);
  function dataEntries(data) {
    if (Array.isArray(data)) return data;
    if (data && typeof data === 'object') return Object.entries(data).map(([key,value]) => value && typeof value === 'object' ? {key,...value} : {key,value});
    return [];
  }
  function stateText(entry) {
    const state = entry.state ?? entry.status;
    if (state === 'fresh' || state === 'ok') return 'Aktuell';
    if (state === 'stale' || entry.stale) return 'Veraltet / Abruffehler';
    if (state === 'missing' || state === 'unavailable' || entry.value == null) return 'Nicht verfügbar';
    return display(state);
  }
  function showData(data) {
    const entries = dataEntries(data.data);
    $('weatherData').innerHTML = entries.map(entry => `<div><span>${escape(entry.title || catalog.infos.find(info => info.key === entry.key)?.title || entry.key)}</span><strong>${escape(display(entry.value))}${entry.unit ? ` ${escape(entry.unit)}` : ''}</strong><small>${escape(stateText(entry))}${entry.source ? ` · ${escape(display(entry.source))}` : ''}</small></div>`).join('') || '<p>Keine Daten verfügbar.</p>';
    $('weatherDataSummary').textContent = `${entries.filter(entry => ['fresh','ok'].includes(entry.state ?? entry.status)).length} von ${entries.length} aktuell`;
    const location=data.location?`${data.location.postcode || ''} ${data.location.country || ''} (${data.location.latitude}, ${data.location.longitude}) · Abruf alle ${data.location.poll_seconds} s`:'konfigurierter Standort';
    $('weatherSource').textContent = `Quelle: ${display(data.source)} · Standort: ${location}${data.sleep?.active || data.sleep === true ? ' · Schlafmodus aktiv' : ''}`;
  }
  $('weatherFields').oninput = mark;
  $('weatherFields').onchange = mark;
  $('weatherModule').onchange = () => {
    if (dirty && !confirm('Ungespeicherte Wetter-Einstellungen verwerfen?')) { $('weatherModule').value = row.id; return; }
    const selected = rows.find(value => String(value.id) === $('weatherModule').value); if (selected) fill(selected);
  };
  $('weatherForm').onsubmit = async event => {
    event.preventDefault(); if (!row || !dirty) return;
    const s = collect();
    if (!s.weather_infos.length || !s.weather_styles.length) { message('Bitte mindestens eine Info und einen Stil auswählen.',true); return; }
    if (s.weather_comfort_min > s.weather_comfort_max) { message('Komforttemperatur: Minimum darf nicht über dem Maximum liegen.',true); return; }
    const target = row; $('saveWeather').disabled = true;
    try {
      const saved = await api(`/api/modules/${target.id}`,{method:'PUT',body:JSON.stringify({...target,settings:s})});
      Object.assign(target,saved); target.settings = {...s,...saved.settings};
      if (row === target) { settings = {...target.settings}; baseline = JSON.stringify(s); mark(); message('Gespeichert. Änderungen gelten ab der nächsten Vorstellung.'); }
      toast('Wetter gespeichert.');
    } catch (error) { message(error.message,true); } finally { $('saveWeather').disabled = false; }
  };
  function stop() { playing = false; pendingFrame = false; clearTimeout(timer); $('weatherPreviewPlay').textContent = '▶ Browser-Vorschau'; }
  function clearFrame() { matrix($('weatherCanvas'),[]); $('weatherFrameData').textContent = ''; $('weatherPreviewStatus').textContent = ''; }
  function browserMode() {
    const demo = $('weatherDemo').checked;
    $('weatherCondition').disabled = !demo; $('weatherIsDay').disabled = !demo;
    $('weatherBrowserSummary').textContent = `${demo ? 'Demo / Simulation' : 'Live'} · nur Browser`;
  }
  // One shared queue serializes browser AND physical previews, with at most four requests per second.
  function sendPreview(payload, valid = () => true) {
    const request = previewQueue.then(async () => {
      const wait = 250 - (performance.now() - lastRequest);
      if (wait > 0) await new Promise(resolve => setTimeout(resolve,wait));
      if (!valid()) return null;
      lastRequest = performance.now();
      return api('/api/weather/preview',{method:'POST',body:JSON.stringify(payload)});
    });
    previewQueue = request.catch(() => {}); return request;
  }
  async function requestFrame() {
    if (!row || document.hidden || !$('weatherBrowserPreview').open) return;
    pendingFrame = true; if (browserBusy) return;
    pendingFrame = false; browserBusy = true; clearTimeout(timer);
    const currentRevision = revision, moduleId = row.id;
    const valid = () => currentRevision === revision && row.id === moduleId && !document.hidden && $('weatherBrowserPreview').open;
    try {
      const elapsed = playing ? Math.min(300,anchor + (performance.now() - start)/1000) : Math.max(0,Math.min(300,Number($('weatherElapsed').value) || 0));
      const demo = $('weatherDemo').checked;
      const payload = {module_id:moduleId,style:$('weatherPreviewStyle').value,info:$('weatherPreviewInfo').value || null,elapsed,physical:false,demo,settings:collect()};
      if (demo) { payload.condition = Number($('weatherCondition').value); payload.is_day = $('weatherIsDay').checked; }
      const data = await sendPreview(payload,valid); if (!data || !valid()) return;
      matrix($('weatherCanvas'),data.pixels || []);
      $('weatherPreviewStatus').textContent = `${demo ? 'Demo / Simulation' : 'Live-Daten'} · nur Browser${demo && !payload.is_day ? ' · Nacht' : ''} · ${data.text || 'Szeneneinstieg'} · ${elapsed.toFixed(1)} s`;
      // Replace rather than append: an offline or changed frame must never retain old status.
      const frameStatus = data.data_status ?? (Array.isArray(data.info) ? data.info.map(entry => `${entry.title || entry.key}: ${stateText(entry)}`).join(' · ') : null);
      $('weatherFrameData').textContent = frameStatus == null ? '' : `Datenstatus: ${display(frameStatus)}`;
      if (playing && elapsed >= Number(data.duration ?? data.duration_seconds ?? 300)) { anchor = 0; start = performance.now(); }
    } catch (error) { if (valid()) { stop(); clearFrame(); $('weatherPreviewStatus').textContent = error.message; } }
    finally { browserBusy = false; if ((playing || pendingFrame) && !document.hidden && $('weatherBrowserPreview').open) timer = setTimeout(requestFrame,250); }
  }
  async function physicalPreview(style, info, status, button) {
    if (!row) return;
    const currentRevision=++physicalRevision,moduleId=row.id;
    button.disabled = true;
    try {
      // Explicit allowlist: no browser condition, day/night, elapsed or demo leakage.
      const result=await sendPreview({module_id:moduleId,style,info,elapsed:0,physical:true,demo:false,settings:collect()},()=>currentRevision===physicalRevision&&row.id===moduleId);
      if (!result || currentRevision!==physicalRevision) return;
      status.textContent = 'LED-Vorschau gestartet · echte Daten · aktuelle Einstellungen.';
    } catch (error) { status.textContent = `${error.message} · Bei Schlafmodus zuerst „Wach“ wählen, dann erneut versuchen.`; }
    finally { button.disabled = false; }
  }
  $('weatherSnapshot').onclick = () => { stop(); requestFrame(); };
  $('weatherPreviewPlay').onclick = () => {
    if (playing) { stop(); return; } if (!row) return;
    playing = true; anchor = Number($('weatherElapsed').value) || 0; start = performance.now(); $('weatherPreviewPlay').textContent = 'Ⅱ Pause'; requestFrame();
  };
  for (const id of ['weatherPreviewStyle','weatherPreviewInfo','weatherDemo','weatherCondition','weatherIsDay','weatherElapsed']) $(id).onchange = () => { stop(); revision++; clearFrame(); browserMode(); requestFrame(); };
  $('weatherPhysical').onclick = () => physicalPreview($('weatherPreviewStyle').value,$('weatherPreviewInfo').value || null,$('weatherPreviewStatus'),$('weatherPhysical'));
  $('weatherBrowserPreview').addEventListener('toggle',() => { if (!$('weatherBrowserPreview').open) { stop(); revision++; clearFrame(); } });
  document.addEventListener('visibilitychange',() => { if (document.hidden) { stop(); revision++; } });
  window.addEventListener('pagehide',() => { stop(); revision++; });
  window.addEventListener('beforeunload',event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
  Promise.all([api('/api/weather'),api('/api/modules')]).then(([data,modules]) => {
    catalog = data; catalog.styles = Array.isArray(data.styles) ? data.styles : []; catalog.infos = Array.isArray(data.infos) ? data.infos : [];
    rows = modules.filter(value => value.key?.split('-')[0] === 'weather'); showData(data);
    $('weatherModule').innerHTML = rows.map(value => `<option value="${escape(value.id)}">${escape(value.name)}</option>`).join('');
    $('weatherPreviewStyle').innerHTML = catalog.styles.map(entry => `<option value="${escape(entry.key)}">${escape(title(entry))}</option>`).join('');
    $('weatherPreviewInfo').innerHTML += catalog.infos.map(entry => `<option value="${escape(entry.key)}">${escape(title(entry))}</option>`).join('');
    if (!catalog.styles.length || !catalog.infos.length) message('Wetter-Katalog noch nicht verfügbar. Bitte später neu laden.');
    else if (rows.length) fill(rows[0]); else message('Kein Wetter-Modul vorhanden. Bitte in der Playlist hinzufügen.');
  }).catch(error => message(error.message,true));
  setInterval(async () => { if (document.hidden || !catalog) return; try { showData(await api('/api/weather')); } catch (_) { $('weatherDataSummary').textContent = 'Abruffehler / veraltet'; } },30000);
})();
