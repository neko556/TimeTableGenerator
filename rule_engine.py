# rule_engine.py
from collections import defaultdict

class RuleEngine:
    """
    Compiles hard and soft constraints from a flat config dict into CP-SAT constraints.

    Input conventions
    - hard_cfg / soft_cfg: dict {rule_id: {enabled, scope, params, weight?}}
    - variables: dict key -> BoolVar where keys look like:
        Phase-1 (cores):    (batch_id, session_id, faculty_id, room_id, t_start)
        Phase-2 (electives):(group_name, session_id, faculty_id, room_id, t_start)
    - occupancy: defaultdict(list) with ("faculty", f, t) or ("room", r, t) aggregations available.

    Produces
    - compile_hard: returns dict {rule_id: assumption BoolVar} if use_assumptions=True else {}
    - compile_soft: returns penalty_terms = list of triples (name, weight_int, BoolVar)
    """
    def __init__(self, time_slot_map, next_slot_map):
        self.time_slot_map = time_slot_map
        self.next_slot_map = next_slot_map

    # ------------- Utilities -------------
    @staticmethod
    def _enabled(entry):
        return bool(entry and entry.get("enabled", False))

    @staticmethod
    def _list_from_scope(scope, key):
        if not scope:
            return []
        v = scope.get(key, [])
        if isinstance(v, str):
            return [s for s in v.split("|") if s]
        return list(v or [])

    @staticmethod
    def _set_from_params(params, key):
        if not params:
            return set()
        raw = params.get(key, "")
        if isinstance(raw, str):
            return set(s for s in raw.split("|") if s)
        return set(raw or [])

    @staticmethod
    def _w100(v, default=1.0):
        try:
            return int(round(float(v) * 100))
        except Exception:
            return int(round(float(default) * 100))

    @staticmethod
    def _day_of(t):
        return str(t).split("_", 1)[0]

    # Normalize variable keys to a common record with fields used by rules
    @staticmethod
    def _iter_assignments(variables):
        for key, var in variables.items():
            # Core: (b, sid, f, r, t)
            # Elective: (g, sid, f, r, t)
            if len(key) != 5:
                continue
            a0, session_id, f_id, r_id, t_start = key
            course_id = str(session_id).split("_S")[0]
            # batch_or_group is the first element (batch_id or group_name)
            yield {
                "scope_id": a0,
                "session_id": session_id,
                "course_id": course_id,
                "faculty_id": f_id,
                "room_id": r_id,
                "t_start": t_start,
                "day": RuleEngine._day_of(t_start),
                "var": var,
            }

    # ------------- Hard rules -------------
    def compile_hard(self, model, variables, occupancy, hard_cfg, use_assumptions=False):
        """
        Returns: assume_on dict for optional rules if use_assumptions=True; else {}
        """
        assume_on = {}

        def gate(rule_id):
            if not use_assumptions:
                return None
            if rule_id not in assume_on:
                a = model.NewBoolVar(f"assume__{rule_id}")
                model.AddAssumption(a)
                assume_on[rule_id] = a
            return assume_on[rule_id]

        # faculty_day_off
        h = hard_cfg.get("faculty_day_off", {})
        if self._enabled(h):
            days = self._set_from_params(h.get("params", {}), "days")
            f_scope = self._list_from_scope(h.get("scope", {}), "faculty_ids")
            f_set = set(f_scope)
            a = gate("faculty_day_off")
            for rec in self._iter_assignments(variables):
                if rec["faculty_id"] in f_set and rec["day"] in days:
                    if a is None:
                        model.Add(rec["var"] == 0)
                    else:
                        model.Add(rec["var"] == 0).OnlyEnforceIf(a)

        # faculty_forbid_slots
        h = hard_cfg.get("faculty_forbid_slots", {})
        if self._enabled(h):
            forbid = self._set_from_params(h.get("params", {}), "forbid_slots")
            f_scope = self._list_from_scope(h.get("scope", {}), "faculty_ids")
            f_set = set(f_scope)
            a = gate("faculty_forbid_slots")
            for rec in self._iter_assignments(variables):
                if rec["faculty_id"] in f_set and rec["t_start"] in forbid:
                    if a is None:
                        model.Add(rec["var"] == 0)
                    else:
                        model.Add(rec["var"] == 0).OnlyEnforceIf(a)

        return assume_on

    # ------------- Soft rules -------------
    def compile_soft(self, model, variables, soft_cfg, occupancy=None):
        """
        Returns a list of penalty terms as triples (name, weight_int, BoolVar)
        """
        terms = []

        # avoid_last_slot
        conf = soft_cfg.get("avoid_last_slot", {})
        if self._enabled(conf):
            last = self._set_from_params(conf.get("params", {}), "last_slot_by_day")
            w = self._w100(conf.get("weight", 1.0), 1.0)
            for rec in self._iter_assignments(variables):
                if rec["t_start"] in last:
                    v = model.NewBoolVar(f"p_last__{rec['scope_id']}__{rec['session_id']}__{rec['t_start']}")
                    model.Add(rec["var"] == 1).OnlyEnforceIf(v)
                    model.Add(rec["var"] == 0).OnlyEnforceIf(v.Not())
                    terms.append(("avoid_last_slot", w, v))

        # avoid_early_slot
        conf = soft_cfg.get("avoid_early_slot", {})
        if self._enabled(conf):
            early = self._set_from_params(conf.get("params", {}), "early_slots")
            w = self._w100(conf.get("weight", 2.0), 2.0)
            for rec in self._iter_assignments(variables):
                if rec["t_start"] in early:
                    v = model.NewBoolVar(f"p_early__{rec['scope_id']}__{rec['session_id']}__{rec['t_start']}")
                    model.Add(rec["var"] == 1).OnlyEnforceIf(v)
                    model.Add(rec["var"] == 0).OnlyEnforceIf(v.Not())
                    terms.append(("avoid_early_slot", w, v))

        # faculty_pref_hours (dispreferred slots)
        conf = soft_cfg.get("faculty_pref_hours", {})
        if self._enabled(conf):
            bad = self._set_from_params(conf.get("params", {}), "dispreferred")
            w = self._w100(conf.get("weight", 2.0), 2.0)
            f_scope = set(self._list_from_scope(conf.get("scope", {}), "faculty_ids"))
            for rec in self._iter_assignments(variables):
                if (not f_scope) or (rec["faculty_id"] in f_scope):
                    if rec["t_start"] in bad:
                        v = model.NewBoolVar(f"p_fac_bad__{rec['scope_id']}__{rec['session_id']}__{rec['faculty_id']}__{rec['t_start']}")
                        model.Add(rec["var"] == 1).OnlyEnforceIf(v)
                        model.Add(rec["var"] == 0).OnlyEnforceIf(v.Not())
                        terms.append(("faculty_dispreferred", w, v))

        # faculty_back_to_back: penalty on consecutive hours per faculty
        conf = soft_cfg.get("faculty_back_to_back", {})
        if self._enabled(conf) and occupancy is not None:
            try:
                window = int(str(conf.get("params", {}).get("window", 2)))
            except Exception:
                window = 2
            w = self._w100(conf.get("weight", 1.5), 1.5)
            # Build S_{f,t} == OR(vars at (f,t)); AtMostOne already makes sum binary
            S = {}
            for (kind, f, t), vs in occupancy.items():
                if kind != "faculty" or not vs:
                    continue
                s = model.NewBoolVar(f"S_fac_{f}_{t}")
                model.Add(sum(vs) >= 1).OnlyEnforceIf(s)
                model.Add(sum(vs) == 0).OnlyEnforceIf(s.Not())
                S[(f, t)] = s
            # Penalize adjacency within window
            for (f, t), s in S.items():
                nxt = t
                count_vars = []
                for _ in range(window - 1):
                    nxt = self.next_slot_map.get(nxt)
                    if nxt is None:
                        break
                    if (f, nxt) in S:
                        b2b = model.NewBoolVar(f"p_b2b_{f}_{t}_{nxt}")
                        s2 = S[(f, nxt)]
                        model.Add(b2b <= s)
                        model.Add(b2b <= s2)
                        model.Add(b2b >= s + s2 - 1)
                        count_vars.append(b2b)
                for v in count_vars:
                    terms.append(("faculty_back_to_back", w, v))

        return terms
 