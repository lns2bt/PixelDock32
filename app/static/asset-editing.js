/* Matching server selection rules; non-destructive until Apply/Import. */
(() => {
  'use strict';
  function plan(durations, options) {
    const {trim_start=0,trim_end=0,step=1,range_kind='frames',start_seconds=0,end_seconds=null}=options;
    if (![trim_start,trim_end,step].every(Number.isInteger) || trim_start<0 || trim_end<0 || step<1 || step>64) throw Error('Ungültige Framezahlen');
    const total=durations.reduce((a,b)=>a+b,0); let start=trim_start,end=durations.length-trim_end;
    if(range_kind==='time') {
      const a=start_seconds*1000,b=end_seconds==null?total:end_seconds*1000;
      if(!Number.isFinite(a)||!Number.isFinite(b)||a<0||a>=b||b>total) throw Error('Zeitbereich muss innerhalb der Animation liegen');
      let position=0;start=null;end=durations.length;
      for(let i=0;i<durations.length;i++){if(start===null&&position+durations[i]>a)start=i;if(position>=b){end=i;break;}position+=durations[i];}
    }
    if(!(start>=0&&start<end&&end<=durations.length))throw Error('Mindestens ein Frame muss erhalten bleiben');
    const groups=[];
    for(let index=start;index<end;index+=step){const duration=durations.slice(index,Math.min(index+step,end)).reduce((a,b)=>a+b,0),parts=Math.ceil(duration/2000),base=Math.floor(duration/parts),extra=duration%parts;
      for(let i=0;i<parts;i++)groups.push({index,duration_ms:base+Number(i<extra)});
    }
    const sum=(a,b)=>durations.slice(a,b).reduce((x,y)=>x+y,0);
    return {start,end,groups,frame_count:groups.length,cycle_ms:sum(start,end),removed_start_ms:sum(0,start),removed_end_ms:sum(end,durations.length),start_ms:sum(0,start),end_ms:sum(0,end)};
  }
  window.AssetEditing={plan};
})();
