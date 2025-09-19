from collections import defaultdict

def build_soft_cfg(constraints):
    """
    Build a normalized soft configuration dict from constraints.json content.
    Returns a dict:
    {
      'avoid_early_slot': {'enabled': bool, 'slots': set[str], 'w': float},
      'avoid_last_slot': {'enabled': bool, 'slots': set[str], 'w': float},
      'faculty_pref_hours': {'enabled': bool, 'dispreferred': set[str], 'scope_fids': set[str], 'w': float},
      'faculty_back_to_back': {'enabled': bool, 'window': int, 'w': float}
    }
    """
    soft = (constraints or {}).get('soft', {})

    cfg = {
        'avoid_early_slot': {
            'enabled': bool(soft.get('avoid_early_slot', {}).get('enabled')),
            'slots': set(soft.get('avoid_early_slot', {}).get('params', {}).get('early_slots', [])),
            'w': float(soft.get('avoid_early_slot', {}).get('weight', 2.0)),
        },
        'avoid_last_slot': {
            'enabled': bool(soft.get('avoid_last_slot', {}).get('enabled')),
            'slots': set(soft.get('avoid_last_slot', {}).get('params', {}).get('last_slot_by_day', [])),
            'w': float(soft.get('avoid_last_slot', {}).get('weight', 1.0)),
        },
        'faculty_pref_hours': {
            'enabled': bool(soft.get('faculty_pref_hours', {}).get('enabled')),
            'dispreferred': set(soft.get('faculty_pref_hours', {}).get('params', {}).get('dispreferred', [])),
            'scope_fids': set(soft.get('faculty_pref_hours', {}).get('scope', {}).get('faculty_ids', [])),
            'w': float(soft.get('faculty_pref_hours', {}).get('weight', 2.0)),
        },
        'faculty_back_to_back': {
            'enabled': bool(soft.get('faculty_back_to_back', {}).get('enabled')),
            'window': int(soft.get('faculty_back_to_back', {}).get('params', {}).get('window', 2)),
            'w': float(soft.get('faculty_back_to_back', {}).get('weight', 1.5)),
        },
    }
    return cfg

def soft_penalty(individual, soft_cfg, next_slot_map, sid_to_course=None):
    """
    Compute soft penalties for a candidate schedule.

    Parameters
    - individual: dict with keys (faculty_id, session_id, time_slot, room_id) -> True
      The presence of a key denotes an assigned atomic slot.
    - soft_cfg: normalized config from build_soft_cfg(...)
    - next_slot_map: dict slot_key -> next slot_key on same day (or None)
    - sid_to_course: optional session_id -> course_id map (not required here)

    Returns: float (lower is better)
    """
    if not individual:
        return 0.0

    total = 0.0

    # Build per-faculty set of occupied slots for adjacency checks
    fac_slots = defaultdict(set)
    for (f_id, sid, t_slot, r_id) in individual.keys():
        fac_slots[f_id].add(t_slot)

    # 1) avoid_early_slot
    se = soft_cfg.get('avoid_early_slot', {})
    if se.get('enabled'):
        early = se.get('slots', set())
        w = float(se.get('w', 2.0))
        if early:
            for (f_id, sid, t_slot, r_id) in individual.keys():
                if t_slot in early:
                    total += w

    # 2) avoid_last_slot
    sl = soft_cfg.get('avoid_last_slot', {})
    if sl.get('enabled'):
        last = sl.get('slots', set())
        w = float(sl.get('w', 1.0))
        if last:
            for (f_id, sid, t_slot, r_id) in individual.keys():
                if t_slot in last:
                    total += w

    # 3) faculty_pref_hours (dispreferred) with scope
    fp = soft_cfg.get('faculty_pref_hours', {})
    if fp.get('enabled'):
        dis = fp.get('dispreferred', set())
        scope = fp.get('scope_fids', set())
        w = float(fp.get('w', 2.0))
        if dis:
            for (f_id, sid, t_slot, r_id) in individual.keys():
                if (not scope or f_id in scope) and (t_slot in dis):
                    total += w

    # 4) faculty_back_to_back within window
    fb = soft_cfg.get('faculty_back_to_back', {})
    if fb.get('enabled'):
        W = max(2, int(fb.get('window', 2)))
        w = float(fb.get('w', 1.5))
        for f_id, slots in fac_slots.items():
            for t0 in list(slots):
                nxt = t0
                for _ in range(W - 1):
                    nxt = next_slot_map.get(nxt)
                    if nxt is None:
                        break
                    if nxt in slots:
                        total += w

    return float(total)
