/* Logarithmic slider, integer fine adjustment, serialized and coalesced writes. */
(() => {
  'use strict';
  const clamp = (value, max) => Math.max(0, Math.min(max, Number.isFinite(Number(value)) ? Number(value) : 0));
  const scale = {
    toValue: position => Math.round(Math.expm1(Math.log(256) * clamp(position,1000) / 1000)),
    toPosition: value => Math.round(Math.log1p(clamp(value,255)) / Math.log(256) * 1000),
  };
  if (typeof module !== 'undefined') module.exports = scale;
  if (typeof window === 'undefined') return;
  window.PixelDockBrightness = { ...scale, mount({api,toast,header}) {
    const trigger = document.createElement('button');
    trigger.className = 'brightness-trigger'; trigger.type = 'button'; trigger.textContent = '☀';
    trigger.setAttribute('aria-label','LED-Helligkeit einstellen'); trigger.setAttribute('aria-expanded','false'); trigger.setAttribute('aria-controls','brightnessPanel');
    header.querySelector('.live-top').append(trigger);
    const panel = document.createElement('section'); panel.id = 'brightnessPanel'; panel.className = 'panel brightness-panel'; panel.hidden = true;
    panel.setAttribute('aria-label','LED-Helligkeit');
    panel.innerHTML = `<div class="section-heading"><h2>LED-Helligkeit</h2><button type="button" class="brightness-close" aria-label="Helligkeit schließen">✕</button></div><label for="brightnessRange">Fein unten, grob oben<input id="brightnessRange" type="range" min="0" max="1000" step="1" value="0" disabled></label><div class="brightness-scale"><span>0 · Aus</span><span>Fein: 1–10</span><span>255</span></div><div class="brightness-exact"><button type="button" id="brightnessMinus" aria-label="Helligkeit um eins verringern" disabled>−1</button><label for="brightnessNumber">Exakter Wert (0–255)<input id="brightnessNumber" type="number" min="0" max="255" step="1" inputmode="numeric" value="0" disabled></label><button type="button" id="brightnessPlus" aria-label="Helligkeit um eins erhöhen" disabled>+1</button></div><div class="brightness-presets" aria-label="Niedrige Helligkeitswerte">${[0,1,3,6,12].map(value=>`<button type="button" data-brightness="${value}" disabled>${value === 0 ? 'Aus' : value}</button>`).join('')}</div><p id="brightnessState" class="muted" role="status">Lade aktuellen Wert …</p><p class="muted">Der Wert bleibt nach Neustarts erhalten. Der Regler wird beim Loslassen angewendet.</p>`;
    header.append(panel);
    const range = panel.querySelector('#brightnessRange'), number = panel.querySelector('#brightnessNumber'), state = panel.querySelector('#brightnessState');
    let value = 0, loaded = false, dirty = false, busy = false, pending = null, revision = 0;
    function show(next, keepThumb = false) {
      value = next; if (!keepThumb) range.value = scale.toPosition(value); number.value = value;
      range.setAttribute('aria-valuetext',value === 0 ? 'Aus, 0 von 255' : `${value} von 255`);
      trigger.textContent = `☀ ${value}`;
      panel.querySelectorAll('[data-brightness]').forEach(button=>button.setAttribute('aria-pressed',String(Number(button.dataset.brightness)===value)));
      panel.querySelector('#brightnessMinus').disabled = !loaded || value === 0;
      panel.querySelector('#brightnessPlus').disabled = !loaded || value === 255;
    }
    async function load() {
      const data = await api('/api/display/brightness');
      if (!dirty && !busy) {
        loaded = true; panel.querySelectorAll('input,button').forEach(node=>node.disabled=false); show(data.brightness);
        state.textContent = data.connected ? 'Aktueller Wert geladen.' : 'Gespeicherter Wert · Uno offline.';
      }
    }
    async function save(next) {
      pending = { value:next, revision };
      if (busy) return;
      busy = true;
      while (pending !== null) {
        const requested = pending; pending = null; state.textContent = 'Wird gespeichert …';
        try {
          await api('/api/display/brightness',{method:'POST',body:JSON.stringify({brightness:requested.value})});
          if (requested.revision === revision && pending === null) { dirty = false; state.textContent = 'Gespeichert.'; }
        } catch (error) {
          state.textContent = error.message;
          toast(error.message,true);
          if (requested.revision === revision && pending === null) dirty = false;
          // Keep the user's target visible. A later adjustment retries normally.
        }
      }
      busy = false;
    }
    function choose(next, apply, keepThumb = false) {
      if (!loaded) return;
      dirty = true; revision++; show(next,keepThumb); state.textContent = apply ? 'Wird gespeichert …' : 'Loslassen zum Anwenden.';
      if (apply) save(value);
    }
    range.oninput = () => choose(scale.toValue(range.value),false,true);
    range.onchange = () => choose(value,true,true);
    number.oninput = () => { dirty = true; revision++; state.textContent = 'Zum Anwenden das Feld verlassen.'; };
    number.onchange = () => {
      const next = Number(number.value);
      if (number.value === '' || !Number.isInteger(next) || next < 0 || next > 255) { toast('Bitte eine ganze Zahl von 0 bis 255 eingeben.',true); show(value); return; }
      choose(next,true);
    };
    panel.querySelector('#brightnessMinus').onclick = () => choose(Math.max(0,value-1),true);
    panel.querySelector('#brightnessPlus').onclick = () => choose(Math.min(255,value+1),true);
    panel.querySelectorAll('[data-brightness]').forEach(button=>button.onclick=()=>choose(Number(button.dataset.brightness),true));
    function close() { panel.hidden = true; trigger.setAttribute('aria-expanded','false'); }
    trigger.onclick = () => {
      panel.hidden = !panel.hidden; trigger.setAttribute('aria-expanded',String(!panel.hidden));
      if (!panel.hidden) load().catch(error=>{state.textContent=error.message;toast(error.message,true);});
    };
    panel.querySelector('.brightness-close').onclick = () => { close(); trigger.focus(); };
    document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!panel.hidden){close();trigger.focus();}});
    document.addEventListener('click',event=>{if(!panel.contains(event.target)&&!trigger.contains(event.target))close();});
    window.addEventListener('pixeldock-status',({detail})=>{
      const current = detail.led_transport?.brightness;
      if (loaded && panel.hidden && !dirty && !busy && Number.isInteger(current)) show(current);
    });
    load().catch(error=>{state.textContent=error.message;});
  }};
})();
