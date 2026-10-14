"""Bounded, non-destructive frame selection with exact retained timing."""
import math

MAX_SOURCE_FRAMES = 4096


def selection_plan(durations, trim_start=0, trim_end=0, step=1,
                   range_kind='frames', start_seconds=0, end_seconds=None):
    if not durations or len(durations) > MAX_SOURCE_FRAMES:
        raise ValueError('1–4096 Quellframes erforderlich')
    for value in (trim_start, trim_end, step):
        if type(value) is not int: raise ValueError('Framezahlen müssen ganze Zahlen sein')
    if trim_start < 0 or trim_end < 0 or not 1 <= step <= 64:
        raise ValueError('Ungültige Kürzung oder Ausdünnung (1–64)')
    if range_kind not in ('frames', 'time'): raise ValueError('Ungültiger Auswahlmodus')
    total = sum(durations)
    start, end = trim_start, len(durations)-trim_end
    if range_kind == 'time':
        try:
            a = float(start_seconds)*1000
            b = total if end_seconds is None else float(end_seconds)*1000
        except (ValueError, TypeError, OverflowError): raise ValueError('Ungültiger Zeitbereich')
        if not math.isfinite(a) or not math.isfinite(b) or not 0 <= a < b <= total:
            raise ValueError('Zeitbereich muss innerhalb der Animation liegen')
        position = 0; start = None; end = len(durations)
        for i, duration in enumerate(durations):
            if start is None and position+duration > a: start=i
            if position >= b: end=i; break
            position += duration
    if not 0 <= start < end <= len(durations):
        raise ValueError('Mindestens ein Frame muss erhalten bleiben')
    groups = []
    for index in range(start,end,step):
        duration = sum(durations[index:min(index+step,end)])
        # Split long holds, never truncate time or create a <33 ms tail.
        parts = math.ceil(duration/2000)
        base, extra = divmod(duration, parts)
        groups.extend({'index':index,'duration_ms':base+int(i<extra)} for i in range(parts))
    return {'start':start,'end':end,'groups':groups,'frame_count':len(groups),
            'cycle_ms':sum(durations[start:end]),'source_cycle_ms':total,
            'removed_start_ms':sum(durations[:start]),'removed_end_ms':sum(durations[end:]),
            'start_ms':sum(durations[:start]),'end_ms':sum(durations[:end])}


def playback_timing(cycle_seconds, duration_seconds, speed=1, mode='limit'):
    try: speed=float(speed)
    except (ValueError, TypeError): speed=1
    if not math.isfinite(speed) or not .1 <= speed <= 4: speed=1
    cycle=cycle_seconds/speed
    if mode=='once': duration=cycle
    elif mode=='finish_loop': duration=math.ceil(duration_seconds/cycle)*cycle
    else: duration=duration_seconds;mode='limit'
    return {'mode':mode,'duration':duration,'cycle_seconds':cycle,'speed':speed}
