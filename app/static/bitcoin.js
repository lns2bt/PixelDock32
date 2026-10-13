/* Preview requests never persist settings or advance the playlist rotation. */
(() => {
  'use strict';
  if (!window.PixelDock) return;
  const {api, matrix, toast} = window.PixelDock, $ = id => document.getElementById(id);
  const escape = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fields = ['bitcoin_stage','bitcoin_max_infos','bitcoin_read_seconds','bitcoin_info_order','bitcoin_style_order','bitcoin_intensity','bitcoin_events','bitcoin_fee_level'];
  let catalog, rows = [], row, settings, infoOrder = [], styleOrder = [], eventOrder = [], baseline, dirty = false;
  let playing = false, inFlight = false, pendingFrame = false, lastRequest = -Infinity, timer, lastFrame = null, anchor = 0, start = 0, previewRevision = 0;
  let durationTimer, durationBusy = false, durationPending = false, durationRevision = 0;
  const ordered = (selected, entries) => [...new Set([...selected, ...entries.map(v => v.key)])].filter(key => entries.some(v => v.key === key));
  function message(text, error = false) { $('bitcoinFeedback').textContent = text; $('bitcoinFeedback').style.color = error ? '#ff9080' : ''; }
  function collect() {
    const result = {...settings};
    for (const key of fields) { const node = $(key); result[key] = node.type === 'checkbox' ? node.checked : node.type === 'number' ? Number(node.value) : node.value; }
    result.bitcoin_infos = infoOrder.filter(key => $(`info_${key}`).checked);
    result.bitcoin_styles = styleOrder.filter(key => $(`style_${key}`).checked);
    result.bitcoin_event_styles = eventOrder.filter(key => $(`event_${key}`).checked);
    return result;
  }
  function summaries(s) {
    $('bitcoinInfosSummary').textContent = `${s.bitcoin_infos.length} ausgewählt · max. ${s.bitcoin_max_infos} pro Vorstellung`;
    $('bitcoinStylesSummary').textContent = `${s.bitcoin_styles.length} von ${catalog.styles.length} ausgewählt`;
    $('bitcoinEventsSummary').textContent = s.bitcoin_events ? `An · ${s.bitcoin_event_styles.length} ausgewählt` : 'Aus';
  }
  function mark() {
    if (!row) return;
    const s = collect(); dirty = JSON.stringify(s) !== baseline;
    $('bitcoinSavebar').hidden = !dirty; $('bitcoinDirty').textContent = dirty ? 'Ungespeichert' : '';
    summaries(s); scheduleDuration();
  }
  function scheduleDuration() {
    if (!row) return;
    durationRevision++; durationPending = false; clearTimeout(durationTimer);
    if (!collect().bitcoin_stage) { $('bitcoinDuration').textContent = `Klassische Playlist-Dauer: ${row.duration_seconds} s.`; return; }
    $('bitcoinDuration').textContent = 'Automatische Dauer wird berechnet …';
    durationTimer = setTimeout(() => { durationPending = true; updateDuration(); }, 200);
  }
  async function updateDuration() {
    if (durationBusy || !durationPending || !row) return;
    durationBusy = true; durationPending = false;
    const revision = durationRevision, moduleId = row.id;
    try {
      const data = await api('/api/bitcoin/duration', {method:'POST', body:JSON.stringify({module_id:moduleId, settings:collect()})});
      if (revision === durationRevision && row.id === moduleId) {
        $('bitcoinDuration').textContent = data.automatic
          ? `${window.PixelDock.bitcoinDurationText(data)} · ${data.info_count} Info${data.info_count === 1 ? '' : 's'} · ${data.read_seconds} s Lesezeit${collect().bitcoin_events ? ` · ggf. +${data.event_extra_seconds} s Blockzeremonie` : ''}.`
          : `Klassische Playlist-Dauer: ${row.duration_seconds} s.`;
      }
    } catch (error) { if (revision === durationRevision) $('bitcoinDuration').textContent = `Dauer nicht verfügbar: ${error.message}`; }
    finally { durationBusy = false; if (durationPending) updateDuration(); }
  }
  function renderInfos() {
    const selected = new Set(settings.bitcoin_infos);
    $('bitcoinInfos').innerHTML = infoOrder.map((key, i) => {
      const info = catalog.infos.find(v => v.key === key);
      return `<div class="bitcoin-row" data-info="${escape(key)}"><div class="row-top"><label class="check"><input type="checkbox" id="info_${escape(key)}" ${selected.has(key) ? 'checked' : ''}>${escape(info.title)}</label><button type="button" data-move="-1" aria-label="${escape(info.title)} nach oben" ${i === 0 ? 'disabled' : ''}>↑</button><button type="button" data-move="1" aria-label="${escape(info.title)} nach unten" ${i === infoOrder.length - 1 ? 'disabled' : ''}>↓</button></div></div>`;
    }).join('');
    $('bitcoinInfos').querySelectorAll('[data-move]').forEach(button => button.onclick = () => {
      settings = collect(); const index = infoOrder.indexOf(button.closest('[data-info]').dataset.info), target = index + Number(button.dataset.move);
      [infoOrder[index], infoOrder[target]] = [infoOrder[target], infoOrder[index]]; renderInfos(); mark();
    });
  }
  function fill(selected) {
    stop(); previewRevision++; row = selected; settings = {...catalog.defaults, ...row.settings};
    infoOrder = ordered(settings.bitcoin_infos, catalog.infos); styleOrder = ordered(settings.bitcoin_styles, catalog.styles); eventOrder = ordered(settings.bitcoin_event_styles, catalog.events);
    for (const key of fields) { const node = $(key); if (node.type === 'checkbox') node.checked = settings[key]; else node.value = settings[key]; }
    renderInfos();
    $('bitcoinStyles').innerHTML = styleOrder.map(key => {
      const style = catalog.styles.find(v => v.key === key);
      return `<div class="bitcoin-row"><div class="row-top"><label class="check"><input id="style_${escape(key)}" type="checkbox" value="${escape(key)}" ${settings.bitcoin_styles.includes(key) ? 'checked' : ''}>${escape(style.title)}</label><button type="button" data-led-style="${escape(key)}" aria-label="${escape(style.title)} auf LEDs zeigen">LED-Vorschau</button><button type="button" data-style="${escape(key)}" aria-label="${escape(style.title)} im Browser zeigen">Browser</button></div><details class="bitcoin-description"><summary>Beschreibung</summary><p class="muted">${escape(style.description)}</p></details></div>`;
    }).join('');
    $('bitcoinStyles').querySelectorAll('[data-style]').forEach(button => button.onclick = () => {
      stop(); previewRevision++; $('bitcoinPreviewStyle').value = button.dataset.style; $('bitcoinElapsed').value = 0; $('bitcoinBrowserPreview').open = true;
      requestFrame(); $('bitcoinCanvas').scrollIntoView({behavior:'auto', block:'center'});
    });
    $('bitcoinStyles').querySelectorAll('[data-led-style]').forEach(button => button.onclick = () => physicalPreview(button.dataset.ledStyle, $('bitcoinLedStatus'), button));
    $('bitcoinEvents').innerHTML = eventOrder.map(key => {
      const event = catalog.events.find(v => v.key === key);
      return `<label class="check"><input id="event_${escape(key)}" type="checkbox" value="${escape(key)}" ${settings.bitcoin_event_styles.includes(key) ? 'checked' : ''}>${escape(event.title)}</label>`;
    }).join('');
    baseline = JSON.stringify(collect()); dirty = false; $('bitcoinSavebar').hidden = true; $('bitcoinDirty').textContent = ''; $('bitcoinFields').disabled = false;
    $('bitcoinLedStatus').textContent = ''; summaries(collect()); scheduleDuration(); message('Bitcoin-Stage geladen.');
  }
  function showData(data) {
    $('bitcoinData').innerHTML = data.data.map(info => `<div><span>${escape(info.title)}</span><strong>${escape(info.value)}</strong><small>${info.state === 'fresh' ? 'Aktuell' : info.state === 'stale' ? 'Veraltet / Abruffehler' : 'Nicht verfügbar'}</small></div>`).join('');
    $('bitcoinDataSummary').textContent = `${data.data.filter(info => info.state === 'fresh').length} von ${data.data.length} aktuell`;
  }
  $('bitcoinFields').oninput = mark;
  $('bitcoinModule').onchange = () => {
    if (dirty && !confirm('Ungespeicherte Bitcoin-Einstellungen verwerfen?')) { $('bitcoinModule').value = row.id; return; }
    fill(rows.find(v => v.id === Number($('bitcoinModule').value)));
  };
  $('bitcoinForm').onsubmit = async event => {
    event.preventDefault(); if (!row || !dirty) return;
    const s = collect();
    if (!s.bitcoin_infos.length || !s.bitcoin_styles.length || s.bitcoin_events && !s.bitcoin_event_styles.length) { message('Bitte mindestens eine Info, eine Szene und ggf. eine Blockzeremonie auswählen.', true); return; }
    const target = row; $('saveBitcoin').disabled = true;
    try {
      const saved = await api(`/api/modules/${target.id}`, {method:'PUT', body:JSON.stringify({name:target.name, enabled:target.enabled, duration_seconds:target.duration_seconds, sort_order:target.sort_order, settings:s})});
      Object.assign(target, saved);
      if (row === target) {
        baseline = JSON.stringify(s); mark();
        message('Gespeichert. Änderungen gelten ab der nächsten Vorstellung.');
      }
      toast('Bitcoin-Stage gespeichert.');
    } catch (error) { message(error.message, true); } finally { $('saveBitcoin').disabled = false; }
  };
  function stop() { playing = false; pendingFrame = false; clearTimeout(timer); $('bitcoinPreviewPlay').textContent = '▶ Browser-Vorschau'; }
  function browserMode() { $('bitcoinBrowserSummary').textContent = `${$('bitcoinDemo').checked || $('bitcoinPreviewEvent').value ? 'Demo / Simulation' : 'Live'} · nur Browser`; }
  async function requestFrame() {
    if (!row || document.hidden || !$('bitcoinBrowserPreview').open) return;
    pendingFrame = true;
    if (inFlight) return;
    clearTimeout(timer);
    const wait = 250 - (performance.now() - lastRequest);
    if (wait > 0) { timer = setTimeout(requestFrame, wait); return; }
    pendingFrame = false; inFlight = true; lastRequest = performance.now();
    const revision = previewRevision, moduleId = row.id;
    try {
      const elapsed = playing ? Math.min(300, anchor + (performance.now() - start) / 1000) : Number($('bitcoinElapsed').value);
      const data = await api('/api/bitcoin/preview', {method:'POST', body:JSON.stringify({module_id:moduleId, style:$('bitcoinPreviewStyle').value, info:$('bitcoinPreviewInfo').value || null, elapsed, physical:false, event:$('bitcoinPreviewEvent').value || null, demo:$('bitcoinDemo').checked, settings:collect()})});
      if (revision !== previewRevision || document.hidden || !$('bitcoinBrowserPreview').open) return;
      const packed = JSON.stringify(data.pixels);
      if (packed !== lastFrame) { matrix($('bitcoinCanvas'), data.pixels); lastFrame = packed; }
      $('bitcoinPreviewStatus').textContent = `${data.demo || $('bitcoinPreviewEvent').value ? 'Demo / Simulation' : 'Live-Daten'} · nur Browser · ${data.text || 'Szeneneinstieg'} · ${elapsed.toFixed(1)} s`;
      if (playing && elapsed >= data.duration) { anchor = 0; start = performance.now(); }
    } catch (error) { if (revision === previewRevision) { stop(); $('bitcoinPreviewStatus').textContent = error.message; } }
    finally { inFlight = false; if ((playing || pendingFrame) && !document.hidden && $('bitcoinBrowserPreview').open) timer = setTimeout(requestFrame, Math.max(0, 250 - (performance.now() - lastRequest))); }
  }
  async function physicalPreview(style, status, button, info = null) {
    if (!row) return;
    button.disabled = true;
    try {
      await api('/api/bitcoin/preview', {method:'POST', body:JSON.stringify({module_id:row.id, style, info, elapsed:0, physical:true, demo:false, event:null, settings:collect()})});
      status.textContent = 'LED-Vorschau gestartet · Live-Daten · aktuelle Einstellungen.';
    } catch (error) { status.textContent = error.message; } finally { button.disabled = false; }
  }
  $('bitcoinSnapshot').onclick = () => { stop(); requestFrame(); };
  $('bitcoinPreviewPlay').onclick = () => {
    if (playing) { stop(); return; } if (!row) return;
    playing = true; anchor = Number($('bitcoinElapsed').value) || 0; start = performance.now(); $('bitcoinPreviewPlay').textContent = 'Ⅱ Pause'; requestFrame();
  };
  for (const id of ['bitcoinPreviewStyle','bitcoinPreviewInfo','bitcoinPreviewEvent','bitcoinDemo']) $(id).onchange = () => { stop(); previewRevision++; $('bitcoinElapsed').value = 0; browserMode(); requestFrame(); };
  $('bitcoinPhysical').textContent = 'LED-Vorschau · Live';
  $('bitcoinPhysical').onclick = () => physicalPreview($('bitcoinPreviewStyle').value, $('bitcoinPreviewStatus'), $('bitcoinPhysical'), $('bitcoinPreviewInfo').value || null);
  $('bitcoinBrowserPreview').addEventListener('toggle', () => { if (!$('bitcoinBrowserPreview').open) { stop(); previewRevision++; } });
  document.addEventListener('visibilitychange', () => { if (document.hidden) { stop(); previewRevision++; } });
  window.addEventListener('pagehide', stop);
  window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
  Promise.all([api('/api/bitcoin'), api('/api/modules')]).then(([data, modules]) => {
    catalog = data; rows = modules.filter(v => v.key.split('-')[0] === 'btc'); showData(data);
    $('bitcoinModule').innerHTML = rows.map(v => `<option value="${v.id}">${escape(v.name)}</option>`).join('');
    $('bitcoinPreviewStyle').innerHTML = data.styles.map(v => `<option value="${escape(v.key)}">${escape(v.title)}</option>`).join('');
    $('bitcoinPreviewInfo').innerHTML = '<option value="">Vorstellung (aktuelle Info-Auswahl)</option>' + data.infos.map(v => `<option value="${escape(v.key)}">${escape(v.title)}</option>`).join('');
    $('bitcoinPreviewEvent').innerHTML += '<optgroup label="Browser-Simulation">' + data.events.map(v => `<option value="${escape(v.key)}">${escape(v.title)}</option>`).join('') + '</optgroup>';
    if (rows.length) fill(rows[0]); else message('Kein Bitcoin-Modul vorhanden. Bitte in der Playlist hinzufügen.');
  }).catch(error => message(error.message, true));
  setInterval(async () => { if (document.hidden || !catalog) return; try { showData(await api('/api/bitcoin')); } catch (_) {} }, 30000);
})();
