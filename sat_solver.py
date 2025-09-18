
import pandas as pd
from collections import defaultdict
from ortools.sat.python import cp_model
from rule_engine import RuleEngine

def check_resource_counts(variables, solver, next_slot_map, day_of, course_details_map):
    """
    Diagnostic helper to verify no resource overlaps exist in the final solution.
    Asserts if any faculty, batch, or room is assigned to more than one session
    in the same time slot, which would indicate a modeling error.
    """
    fac_counts, batch_counts, room_counts = defaultdict(int), defaultdict(int), defaultdict(int)
    for key, var in variables.items():
        if not solver.BooleanValue(var):
            continue

        # Handle different key structures for core vs. elective models
        if len(key) == 5 and isinstance(key[0], str) and key[0].startswith("BE-IT"):
             b_id, sess_id, f_id, r_id, t_start = key
             entity_id = ('batch', b_id)
        elif len(key) == 5:
             g_name, sess_id, f_id, r_id, t_start = key
             entity_id = ('group', g_name)
        else:
            continue

        course_id = sess_id.split('_S')[0]
        duration = course_details_map.get(course_id, {}).get('duration', 1)
        current = t_start
        start_day = day_of(t_start)

        for _ in range(int(duration)):
            if (not current) or (day_of(current) != start_day):
                break
            
            if entity_id[0] == 'batch':
                batch_counts[(entity_id[1], current)] += 1
            fac_counts[(f_id, current)] += 1
            room_counts[(r_id, current)] += 1
            current = next_slot_map.get(current)
            
    return fac_counts, batch_counts, room_counts


class BatchTimetableSATModel:
    def __init__(self, data, batches, batch_sessions, time_slot_map, next_slot_map,
                 occupied_slots=None, allow_unscheduled=False):
        self.data = data
        self.batches = batches
        self.batch_sessions = batch_sessions
        self.time_slot_map = time_slot_map
        self.next_slot_map = next_slot_map
        self.allow_unscheduled = allow_unscheduled
        self.occupied_faculty_slots = occupied_slots.get('faculty', defaultdict(set)) if occupied_slots else defaultdict(set)
        self.occupied_room_slots = occupied_slots.get('room', defaultdict(set)) if occupied_slots else defaultdict(set)

    @staticmethod
    def _is_available_flag(x):
        return str(x).strip().lower() in ('available', 'yes', 'true', '1', 'y')

    @staticmethod
    def _day_of(slot):
        return str(slot).split('_', 1)[0]

    def _build_availability_maps(self):
        faculty_availability = defaultdict(set)
        for _, row in self.data.get('faculty_availability', pd.DataFrame()).iterrows():
            if self._is_available_flag(row.get('availability_type')):
                start = pd.to_datetime(row['time_slot_start']).time()
                end = pd.to_datetime(row['time_slot_end']).time()
                for slot in self.time_slot_map:
                    day, times = slot.split('_')
                    if row['day_of_week'] == day and start <= pd.to_datetime(times.split('-')[0]).time() < end:
                        faculty_availability[row['faculty_id']].add(slot)

        room_availability = defaultdict(set)
        for _, row in self.data.get('room_availability', pd.DataFrame()).iterrows():
            if self._is_available_flag(row.get('availability_status')):
                start = pd.to_datetime(row['time_slot_start']).time()
                end = pd.to_datetime(row['time_slot_end']).time()
                for slot in self.time_slot_map:
                    day, times = slot.split('_')
                    if row['day_of_week'] == day and start <= pd.to_datetime(times.split('-')[0]).time() < end:
                        room_availability[row['room_id']].add(slot)
                        
        return faculty_availability, room_availability

    def _get_course_details_map(self):
        details = {}
        for _, c in self.data.get('courses', pd.DataFrame()).iterrows():
            is_lab = 'lab' in str(c.get('course_type', '')).lower()
            details[c['course_id']] = {
                'duration': int(c.get('duration_hours', 2)) if is_lab else 1,
                'is_lab': is_lab
            }
        return details

    def solve(self,
              time_limit=180,
              elective_reservations=None,
              global_elective_windows=None,
              hard_cfg=None,
              soft_cfg=None,
              use_assumptions=False):
        
        model = cp_model.CpModel()
        variables, session_vars, unsched_vars = {}, defaultdict(list), {}
        
        fac_avail, room_avail = self._build_availability_maps()
        course_details_map = self._get_course_details_map()
        
        expertise_map = defaultdict(list)
        for _, row in self.data['faculty_expertise'].iterrows():
            expertise_map[row['course_id']].append(row['faculty_id'])
            
        all_starts = list(self.time_slot_map.keys())

        print("  - Building model variables and session constraints...")
        for b_id, sessions in self.batch_sessions.items():
            batch_size = len(self.batches.get(b_id, []))
            for session_id in sessions:
                course_id = session_id.split('_S')[0]
                details = course_details_map.get(course_id)
                if not details: continue
                
                duration, is_lab = details['duration'], details['is_lab']
                for f_id in expertise_map.get(course_id, []):
                    for _, room in self.data['rooms'].iterrows():
                        r_id, room_type, room_cap = room['room_id'], str(room.get('room_type', '')).lower(), int(room.get('capacity', 0))
                        
                        if (is_lab and 'lab' not in room_type) or \
                           (not is_lab and 'lab' in room_type) or \
                           (room_cap < batch_size):
                            continue
                            
                        for t_start in all_starts:
                            is_valid, current = True, t_start
                            start_day = self._day_of(t_start)
                            for _ in range(duration):
                                if not current or self._day_of(current) != start_day or \
                                   current in self.occupied_faculty_slots.get(f_id, set()) or \
                                   current in self.occupied_room_slots.get(r_id, set()) or \
                                   current not in fac_avail.get(f_id, set()) or \
                                   current not in room_avail.get(r_id, set()):
                                    is_valid = False
                                    break
                                current = self.next_slot_map.get(current)
                            
                            if is_valid:
                                key = (b_id, session_id, f_id, r_id, t_start)
                                var = model.NewBoolVar(f"v_{b_id}_{session_id}_{f_id}_{r_id}_{t_start}")
                                variables[key] = var
                                session_vars[(b_id, session_id)].append(var)

        for (b_id, session_id), vars_list in session_vars.items():
            if vars_list:
                if self.allow_unscheduled:
                    y = model.NewBoolVar(f"unsched_{b_id}_{session_id}")
                    unsched_vars[(b_id, session_id)] = y
                    model.AddExactlyOne(vars_list + [y])
                else:
                    model.AddExactlyOne(vars_list)
            elif not self.allow_unscheduled:
                print(f"  - ❌ UNSCHEDULABLE: {(b_id, session_id)} has ZERO candidates.")
                return [], {'faculty': self.occupied_faculty_slots, 'room': self.occupied_room_slots}, False, {}

        print("  - Building global constraints (no double-booking)...")
        occupancy = defaultdict(list)
        for (b_id, sess_id, f_id, r_id, t_start), var in variables.items():
            course_id = sess_id.split('_S')[0]
            duration = course_details_map.get(course_id, {}).get('duration', 1)
            current, start_day = t_start, self._day_of(t_start)
            for _ in range(int(duration)):
                if not current or self._day_of(current) != start_day: break
                occupancy[('batch', b_id, current)].append(var)
                occupancy[('faculty', f_id, current)].append(var)
                occupancy[('room', r_id, current)].append(var)
                current = self.next_slot_map.get(current)
        
        for vs in occupancy.values():
            if len(vs) > 1:
                model.AddAtMostOne(vs)

        penalty_terms = []
        engine = RuleEngine(self.time_slot_map, self.next_slot_map)
        penalty_terms.extend(engine.compile_soft(model, variables, soft_cfg or {}, occupancy=occupancy))
        engine.compile_hard(model, variables, occupancy, hard_cfg or {}, use_assumptions=use_assumptions)

        if self.allow_unscheduled and unsched_vars:
            penalty_terms.extend([("unscheduled", 1000, y) for y in unsched_vars.values()])
        
        if penalty_terms:
            model.Minimize(sum(w * v for (_, w, v) in penalty_terms))

        y_reserve, z_global = {}, None
        if global_elective_windows is not None:
            print("  - Adding GLOBAL elective reservation windows...")
            z_global = {t: model.NewBoolVar(f"z__{t}") for t in self.time_slot_map.keys()}
            model.Add(sum(z_global.values()) == int(global_elective_windows))
            for b_id in self.batches.keys():
                for t in self.time_slot_map.keys():
                    y = model.NewBoolVar(f"reserve__{b_id}__{t}")
                    y_reserve[(b_id, t)] = y
                    model.Add(y == z_global[t])
                    core_at_bt = occupancy.get(('batch', b_id, t), [])
                    model.AddAtMostOne(core_at_bt + [y])
        elif elective_reservations:
            print("  - Adding per-batch elective reservation variables...")
            for b_id, E_b in elective_reservations.items():
                batch_res_vars = []
                for t in self.time_slot_map.keys():
                    y = model.NewBoolVar(f"reserve__{b_id}__{t}")
                    y_reserve[(b_id, t)] = y
                    batch_res_vars.append(y)
                    core_at_bt = occupancy.get(('batch', b_id, t), [])
                    model.AddAtMostOne(core_at_bt + [y])
                model.Add(sum(batch_res_vars) == int(E_b))

        print(f"--- Solving Unified Model ({len(variables)} variables) ---")
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit)
        solver.parameters.log_search_progress = True
        status = solver.Solve(model)

        schedule, occupied_slots, reserved_slots_by_batch = [], {'faculty': defaultdict(set), 'room': defaultdict(set)}, defaultdict(set)
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            print("  - ✅ SOLVED Unified Model")
            
            # This check should now pass.
            fac, bat, rm = check_resource_counts(variables, solver, self.next_slot_map, self._day_of, course_details_map)
            assert all(c <= 1 for c in fac.values()), "FATAL: Faculty overlap detected post-solve."
            assert all(c <= 1 for c in bat.values()), "FATAL: Batch overlap detected post-solve."
            assert all(c <= 1 for c in rm.values()), "FATAL: Room overlap detected post-solve."

            if global_elective_windows is not None and z_global is not None:
                chosen = {t for t, zt in z_global.items() if solver.Value(zt) == 1}
                for b_id in self.batches.keys():
                    reserved_slots_by_batch[b_id] = set(chosen)
            elif elective_reservations:
                for (b_id, t_start), y in y_reserve.items():
                    if solver.Value(y) == 1:
                        reserved_slots_by_batch.setdefault(b_id, set()).add(t_start)
                        
            for key, var in variables.items():
                if solver.Value(var) == 1:
                    b_id, session_id, f_id, r_id, t_start = key
                    course_id = session_id.split('_S')[0]
                    schedule.append((f_id, course_id, t_start, r_id, b_id))
                    duration = course_details_map.get(course_id, {}).get('duration', 1)
                    current, start_day = t_start, self._day_of(t_start)
                    for _ in range(duration):
                        if not current or self._day_of(current) != start_day: break
                        occupied_slots['faculty'][f_id].add(current)
                        occupied_slots['room'][r_id].add(current)
                        current = self.next_slot_map.get(current)
                        
            return schedule, occupied_slots, True, reserved_slots_by_batch
        else:
            print("  - ❌ FAILED to solve the unified model.")
            return schedule, occupied_slots, False, {}

    def solve_electives(self, elective_groups, elective_group_sessions,
                      core_reserved, core_batches, occupied_slots=None,
                      time_limit=60, allow_unscheduled=True, hard_cfg=None, soft_cfg=None):
        
        print("\n--- Initializing Elective Solver ---")
        if not any(elective_group_sessions.values()):
            print("[info] No elective sessions to schedule; skipping Phase 2.")
            return [], occupied_slots or {}, True

        model = cp_model.CpModel()
        variables, session_vars, unsched_vars = {}, defaultdict(list), {}
        
        fac_avail, room_avail = self._build_availability_maps()
        course_details_map = self._get_course_details_map()
        
        expertise_map = defaultdict(list)
        for _, row in self.data['faculty_expertise'].iterrows():
            expertise_map[row['course_id']].append(row['faculty_id'])

        pre_fac = occupied_slots.get('faculty', defaultdict(set))
        pre_room = occupied_slots.get('room', defaultdict(set))

        group_to_batches = {
            g: [b for b, roster in core_batches.items() if any(s in roster for s in students)]
            for g, students in elective_groups.items()
        }

        allowed_slots_per_group = {}
        for g, batches in group_to_batches.items():
            sets = [core_reserved.get(b, set()) for b in batches]
            inter = set.intersection(*sets) if sets else set()
            allowed = inter if inter else set.union(*sets)
            allowed_slots_per_group[g] = allowed
            
        print("  - Building elective variables and session constraints...")
        for g_name, sessions in elective_group_sessions.items():
            group_size = len(elective_groups.get(g_name, []))
            for session_id in sessions:
                course_id = session_id.split('_S')[0]
                details = course_details_map.get(course_id)
                if not details: continue
                
                duration, is_lab = details['duration'], details['is_lab']
                allowed_starts = allowed_slots_per_group.get(g_name, set())

                for f_id in expertise_map.get(course_id, []):
                    for _, room in self.data['rooms'].iterrows():
                        r_id, room_type, room_cap = room['room_id'], str(room.get('room_type', '')).lower(), int(room.get('capacity', 0))
                        
                        if (is_lab and 'lab' not in room_type) or \
                           (not is_lab and 'lab' not in room_type) or \
                           (room_cap < group_size):
                            continue
                        
                        for t_start in allowed_starts:
                            is_valid, current = True, t_start
                            start_day = self._day_of(t_start)
                            for _ in range(duration):
                                if not current or self._day_of(current) != start_day or \
                                   current in pre_fac.get(f_id, set()) or \
                                   current in pre_room.get(r_id, set()) or \
                                   current not in fac_avail.get(f_id, set()) or \
                                   current not in room_avail.get(r_id, set()):
                                    is_valid = False; break
                                current = self.next_slot_map.get(current)
                            
                            if is_valid:
                                key = (g_name, session_id, f_id, r_id, t_start)
                                var = model.NewBoolVar(f"e_{g_name}_{session_id}_{f_id}_{r_id}_{t_start}")
                                variables[key] = var
                                session_vars[(g_name, session_id)].append(var)

        for (g_name, session_id), vars_list in session_vars.items():
            if vars_list:
                if allow_unscheduled:
                    y = model.NewBoolVar(f"unsched_{g_name}_{session_id}")
                    unsched_vars[(g_name, session_id)] = y
                    model.AddExactlyOne(vars_list + [y])
                else:
                    model.AddExactlyOne(vars_list)
            elif not allow_unscheduled:
                print(f"  - ❌ UNSCHEDULABLE Elective: {(g_name, session_id)} has ZERO candidates.")
                return [], occupied_slots, False
        
        occupancy = defaultdict(list)
        for (g_name, sess_id, f_id, r_id, t_start), var in variables.items():
            course_id = sess_id.split('_S')[0]
            duration = course_details_map.get(course_id, {}).get('duration', 1)
            current, start_day = t_start, self._day_of(t_start)
            for _ in range(int(duration)):
                if not current or self._day_of(current) != start_day: break
                occupancy[('faculty', f_id, current)].append(var)
                occupancy[('room', r_id, current)].append(var)
                current = self.next_slot_map.get(current)
        
        for vs in occupancy.values():
            if len(vs) > 1:
                model.AddAtMostOne(vs)

        penalty_terms = []
        engine = RuleEngine(self.time_slot_map, self.next_slot_map)
        penalty_terms.extend(engine.compile_soft(model, variables, soft_cfg or {}, occupancy=occupancy))
        engine.compile_hard(model, variables, occupancy, hard_cfg or {}, use_assumptions=False)
        
        if allow_unscheduled and unsched_vars:
            penalty_terms.extend([("unsched_elec", 1000, y) for y in unsched_vars.values()])
            
        if penalty_terms:
            model.Minimize(sum(w * v for (_, w, v) in penalty_terms))

        print(f"--- Solving Elective Model ({len(variables)} variables) ---")
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit)
        solver.parameters.log_search_progress = True
        status = solver.Solve(model)

        elective_schedule = []
        updated_occ = {'faculty': pre_fac.copy(), 'room': pre_room.copy()}
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            print("  - ✅ SOLVED Elective Model")
            for key, var in variables.items():
                if solver.Value(var) == 1:
                    g_name, session_id, f_id, r_id, t_start = key
                    course_id = session_id.split('_S')[0]
                    elective_schedule.append((f_id, course_id, t_start, r_id, g_name))
                    duration = course_details_map.get(course_id, {}).get('duration', 1)
                    current, start_day = t_start, self._day_of(t_start)
                    for _ in range(duration):
                        if not current or self._day_of(current) != start_day: break
                        updated_occ['faculty'][f_id].add(current)
                        updated_occ['room'][r_id].add(current)
                        current = self.next_slot_map.get(current)
            return elective_schedule, updated_occ, True
        else:
            print("  - ❌ FAILED to solve the elective model.")
            return elective_schedule, updated_occ, False

