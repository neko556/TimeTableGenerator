import pandas as pd
from collections import defaultdict
from ortools.sat.python import cp_model




class BatchTimetableSATModel:
    def __init__(self, data, batches, batch_sessions, time_slot_map, next_slot_map,
                 occupied_slots=None, allow_unscheduled=False):
        self.data = data
        self.batches = batches                      # core batches (Phase 1)
        self.batch_sessions = batch_sessions        # core sessions (Phase 1)
        self.time_slot_map = time_slot_map
        self.next_slot_map = next_slot_map
        self.allow_unscheduled = allow_unscheduled  # strict vs soft for Phase 1
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

    def solve(self, time_limit=180, elective_reservations=None, global_elective_windows=None):
        """
        Phase 1: Solve cores and reserve elective capacity.
        Use either:
        - global_elective_windows: int E_global (shared z_t across all batches), or
        - elective_reservations: dict {batch_id: E_b} (per-batch y[b,t]).
        Returns: (schedule, occupied_slots, ok, reserved_slots_by_batch)
        """
        print("\n--- Initializing Unified Solver ---")
        fac_avail, room_avail = self._build_availability_maps()  # availability sets [web:14]
        course_details_map = self._get_course_details_map()       # duration/is_lab map [web:14]

        # course -> faculty list
        expertise_map = defaultdict(list)
        for _, row in self.data['faculty_expertise'].iterrows():
            expertise_map[row['course_id']].append(row['faculty_id'])  # standard mapping [web:14]

        model = cp_model.CpModel()
        variables = {}                    # (b, sess, f, r, t) -> BoolVar [web:34]
        session_vars = defaultdict(list)  # per-session AddExactlyOne [web:34]
        unsched_vars = {}                 # optional soft-unscheduled bools [web:14]
        all_starts = list(self.time_slot_map.keys())

        print("  - Building model variables and session constraints...")
        for b_id, sessions in self.batch_sessions.items():
            batch_size = len(self.batches.get(b_id, []))
            for session_id in sessions:
                course_id = session_id.split('_S')[0]
                details = course_details_map.get(course_id)
                if not details:
                    continue
                duration = details['duration']
                is_lab = details['is_lab']

                for f_id in expertise_map.get(course_id, []):
                    for _, room in self.data['rooms'].iterrows():
                        r_id = room['room_id']
                        room_type = str(room.get('room_type', '')).lower()
                        room_cap = int(room.get('capacity', 0))
                        if (is_lab and 'lab' not in room_type) or (not is_lab and 'lab' in room_type) or (room_cap < batch_size):
                            continue
                        for t_start in all_starts:
                            is_valid, current = True, t_start
                            start_day = self._day_of(t_start)
                            for _ in range(duration):
                                if (not current) or (self._day_of(current) != start_day):
                                    is_valid = False; break
                                if current in self.occupied_faculty_slots.get(f_id, set()):
                                    is_valid = False; break
                                if current in self.occupied_room_slots.get(r_id, set()):
                                    is_valid = False; break
                                if current not in fac_avail.get(f_id, set()):
                                    is_valid = False; break
                                if current not in room_avail.get(r_id, set()):
                                    is_valid = False; break
                                current = self.next_slot_map.get(current)
                            if is_valid:
                                key = (b_id, session_id, f_id, r_id, t_start)
                                var = model.NewBoolVar(f"v_{b_id}__{session_id}__{f_id}__{r_id}__{t_start}")  # Bool var [web:34]
                                variables[key] = var
                                session_vars[(b_id, session_id)].append(var)

        # Session completeness (hard or soft)
        for (b_id, session_id), vars_list in session_vars.items():
            if vars_list:
                if self.allow_unscheduled:
                    y = model.NewBoolVar(f"unsched__{b_id}__{session_id}")
                    unsched_vars[(b_id, session_id)] = y
                    model.AddExactlyOne(vars_list + [y])  # AddExactlyOne pattern [web:34]
                else:
                    model.AddExactlyOne(vars_list)        # hard coverage [web:34]
            else:
                if self.allow_unscheduled:
                    y = model.NewBoolVar(f"unsched__{b_id}__{session_id}")
                    unsched_vars[(b_id, session_id)] = y
                    model.AddExactlyOne([y])
                    print(f"  - ⚠ Empty domain: {(b_id, session_id)} marked unscheduled")  # diagnostic [web:14]
                else:
                    print(f"  - ❌ UNSCHEDULABLE before solve: {(b_id, session_id)} has ZERO candidates")  # fail fast [web:14]
                    return [], {'faculty': self.occupied_faculty_slots, 'room': self.occupied_room_slots}, False, {}

        # Diagnostics gate
        total_sessions = len(session_vars)
        total_vars = len(variables)
        print(f"Core sessions modeled: {total_sessions}, assignment vars: {total_vars}")  # sanity check [web:14]
        if total_vars == 0:
            print("NO DECISION VARS: check preprocessing and candidate filters.")          # guard [web:14]
            return [], {'faculty': self.occupied_faculty_slots, 'room': self.occupied_room_slots}, False, {}

        # No double-booking across batch/faculty/room (AtMostOne) [web:14]
        print("  - Building global constraints (no double-booking)...")
        occupancy = defaultdict(list)
        for (b_id, session_id, f_id, r_id, t_start), var in variables.items():
            course_id = session_id.split('_S')[0]
            duration = course_details_map.get(course_id, {}).get('duration', 1)
            current = t_start
            start_day = self._day_of(t_start)
            for _ in range(duration):
                if (not current) or (self._day_of(current) != start_day):
                    break
                occupancy[('batch', b_id, current)].append(var)
                occupancy[('faculty', f_id, current)].append(var)
                occupancy[('room', r_id, current)].append(var)
                current = self.next_slot_map.get(current)
        for vs in occupancy.values():
            if len(vs) > 1:
                model.AddAtMostOne(vs)  # AtMostOne encoding [web:34]

        # Elective reservations: global windows z_t or per-batch y[b,t] with channeling [web:52]
        y_reserve = {}
        z_global = None
        if global_elective_windows is not None:
            print("  - Adding GLOBAL elective reservation windows...")
            z_global = {t: model.NewBoolVar(f"z__{t}") for t in self.time_slot_map.keys()}    # z_t windows [web:52]
            model.Add(sum(z_global.values()) == int(global_elective_windows))                  # exact count [web:52]
            for b_id in self.batches.keys():
                for t in self.time_slot_map.keys():
                    y = model.NewBoolVar(f"reserve__{b_id}__{t}")
                    y_reserve[(b_id, t)] = y
                    model.Add(y == z_global[t])                                               # channel y[b,t]==z_t [web:52]
                    core_at_bt = occupancy.get(('batch', b_id, t), [])
                    model.AddAtMostOne(core_at_bt + [y])                                      # batch cannot use core+reserve [web:52]
        elif elective_reservations:
            print("  - Adding per-batch elective reservation variables...")
            for b_id, E_b in elective_reservations.items():
                for t in self.time_slot_map.keys():
                    y = model.NewBoolVar(f"reserve__{b_id}__{t}")
                    y_reserve[(b_id, t)] = y
                    core_at_bt = occupancy.get(('batch', b_id, t), [])
                    model.AddAtMostOne(core_at_bt + [y])                                      # channel [web:52]
                model.Add(sum(y_reserve[(b_id, t)] for t in self.time_slot_map.keys()) == int(E_b))  # exact per batch [web:52]

        # Objective (optional soft unscheduled) [web:14]
        if self.allow_unscheduled and unsched_vars:
            model.Minimize(sum(unsched_vars.values()))  # linear objective on BoolVars [web:34]

        print(f"--- Solving Unified Model ({len(variables)} variables) ---")
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit)   # time bound [web:14]
        solver.parameters.log_search_progress = False              # logs [web:14]
        status = solver.Solve(model)                                # solve [web:14]

        schedule = []
        occupied_slots = {'faculty': self.occupied_faculty_slots, 'room': self.occupied_room_slots}
        reserved_slots_by_batch = {}
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            # collect reservations [web:52]
            if global_elective_windows is not None and z_global is not None:
                chosen = {t for t, zt in z_global.items() if solver.Value(zt) == 1}
                for b_id in self.batches.keys():
                    reserved_slots_by_batch[b_id] = set(chosen)      # same z_t for all batches [web:52]
            elif elective_reservations:
                for (b_id, t_start), y in y_reserve.items():
                    if solver.Value(y) == 1:
                        reserved_slots_by_batch.setdefault(b_id, set()).add(t_start)  # per-batch [web:52]

            print("  - SOLVED Unified Model")  # success [web:14]
            if self.allow_unscheduled and unsched_vars:
                n_unsched = sum(int(solver.Value(v)) for v in unsched_vars.values())
                print(f"  - Unscheduled sessions (minimized): {n_unsched}")  # objective value [web:14]

            # extract chosen core assignments [web:14]
            for key, var in variables.items():
                if solver.Value(var) == 1:
                    b_id, session_id, f_id, r_id, t_start = key
                    course_id = session_id.split('_S')[0]
                    schedule.append((f_id, course_id, t_start, r_id, b_id))
                    duration = course_details_map.get(course_id, {}).get('duration', 1)
                    current = t_start
                    start_day = self._day_of(t_start)
                    for _ in range(duration):
                        if (not current) or (self._day_of(current) != start_day):
                            break
                        occupied_slots['faculty'][f_id].add(current)
                        occupied_slots['room'][r_id].add(current)
                        current = self.next_slot_map.get(current)

            return schedule, occupied_slots, True, reserved_slots_by_batch  # return with reservations [web:52]
        else:
            print("  - FAILED to solve the unified model.")  # failure [web:14]
            return schedule, occupied_slots, False, {}



    # ------------------------ Phase 2: Electives ------------------------
    def solve_electives(self, elective_groups, elective_group_sessions,
                    core_reserved, core_batches, occupied_slots=None,
                    time_limit=60, allow_unscheduled=True):
        print("\n--- Initializing Elective Solver ---")
        fac_avail, room_avail = self._build_availability_maps()
        course_details_map = self._get_course_details_map()

        # course -> faculty list
        expertise_map = defaultdict(list)
        for _, row in self.data['faculty_expertise'].iterrows():
            expertise_map[row['course_id']].append(row['faculty_id'])

        pre_fac = occupied_slots.get('faculty', defaultdict(set)) if occupied_slots else defaultdict(set)
        pre_room = occupied_slots.get('room', defaultdict(set)) if occupied_slots else defaultdict(set)

        intended_sessions = sum(len(s) for s in elective_group_sessions.values())
        print(f"Elective intended sessions: {intended_sessions}")
        if intended_sessions == 0:
            print("[info] No elective sessions to schedule; skipping Phase 2.")
            return [], occupied_slots or {'faculty': pre_fac, 'room': pre_room}, True

        # group -> batches containing any member
        group_to_batches = {
            g: [b for b, roster in core_batches.items() if any(s in roster for s in students)]
            for g, students in elective_groups.items()
        }

        # Allowed slots per group (intersection fallback to union)
        allowed_slots_per_group = {}
        for g, batches in group_to_batches.items():
            sets = [core_reserved.get(b, set()) for b in batches]
            inter = set.intersection(*sets) if sets else set()
            allowed = inter if inter else set().union(*sets)
            allowed_slots_per_group[g] = allowed
            print(f"[elective-domain] {g}: batches={batches}, allowed_slots={len(allowed)}")

        model = cp_model.CpModel()
        variables = {}                    # (g, sess, f, r, t) -> BoolVar
        session_vars = defaultdict(list)  # (g, sess) -> [BoolVar]
        unsched_vars = {}

        print("  - Building elective variables and session constraints...")
        for g_name, sessions in elective_group_sessions.items():
            group_size = len(elective_groups.get(g_name, []))
            for session_id in sessions:
                _ = session_vars[(g_name, session_id)]  # pre-seed
                course_id = session_id.split('_S')[0]
                details = course_details_map.get(course_id)
                if not details:
                    print(f"[elective-zero] group={g_name} session={session_id} reason=no_course_details")
                    continue
                duration = details['duration']
                is_lab = details['is_lab']

                faculty_count = len(expertise_map.get(course_id, []))
                rooms_ok_count = 0
                seen_room = set()

                allowed_starts = allowed_slots_per_group.get(g_name, set())
                cand_count = 0

                for f_id in expertise_map.get(course_id, []):
                    for _, room in self.data['rooms'].iterrows():
                        r_id = room['room_id']
                        room_type = str(room.get('room_type', '')).lower()
                        room_cap = int(room.get('capacity', 0))
                        ok_room = ((is_lab and 'lab' in room_type) or (not is_lab and 'lab' not in room_type)) and (room_cap >= group_size)
                        if not ok_room:
                            continue
                        if r_id not in seen_room:
                            rooms_ok_count += 1
                            seen_room.add(r_id)
                        for t_start in allowed_starts:
                            is_valid, current = True, t_start
                            start_day = str(t_start).split('_', 1)[0]
                            for _ in range(duration):
                                if (not current) or (str(current).split('_', 1)[0] != start_day):
                                    is_valid = False; break
                                if current in pre_fac.get(f_id, set()):
                                    is_valid = False; break
                                if current in pre_room.get(r_id, set()):
                                    is_valid = False; break
                                if current not in fac_avail.get(f_id, set()):
                                    is_valid = False; break
                                if current not in room_avail.get(r_id, set()):
                                    is_valid = False; break
                                current = self.next_slot_map.get(current)
                            if is_valid:
                                key = (g_name, session_id, f_id, r_id, t_start)
                                var = model.NewBoolVar(f"e_{g_name}__{session_id}__{f_id}__{r_id}__{t_start}")
                                variables[key] = var
                                session_vars[(g_name, session_id)].append(var)
                                cand_count += 1

                if cand_count == 0:
                    print(f"[elective-zero] group={g_name} session={session_id} "
                        f"faculty={faculty_count} rooms_ok={rooms_ok_count} allowed_starts={len(allowed_starts)}")

        # Per-session coverage (soft unscheduled optional)
        for (g_name, session_id), vars_list in session_vars.items():
            if vars_list:
                model.AddExactlyOne(vars_list)
            else:
                if allow_unscheduled:
                    y = model.NewBoolVar(f"unsched__{g_name}__{session_id}")
                    unsched_vars[(g_name, session_id)] = y
                    model.AddExactlyOne([y])
                else:
                    print(f"  - UNSCHEDULABLE elective session: {(g_name, session_id)} has ZERO candidates")
                    return [], occupied_slots or {'faculty': pre_fac, 'room': pre_room}, False

        total_sessions = len(session_vars)
        total_vars = len(variables)
        print(f"Elective sessions modeled: {total_sessions} / intended: {intended_sessions}, assignment vars: {total_vars}")

        # Resource-only no-overlap (faculty and room)
        print("  - Building global constraints (no double-booking for electives)...")
        occupancy = defaultdict(list)
        for (g_name, session_id, f_id, r_id, t_start), var in variables.items():
            course_id = session_id.split('_S')[0]
            duration = course_details_map.get(course_id, {}).get('duration', 1)
            current = t_start
            start_day = str(t_start).split('_', 1)[0]
            for _ in range(duration):
                if (not current) or (str(current).split('_', 1)[0] != start_day):
                    break
                occupancy[('faculty', f_id, current)].append(var)
                occupancy[('room', r_id, current)].append(var)
                current = self.next_slot_map.get(current)
        for vs in occupancy.values():
            if len(vs) > 1:
                model.AddAtMostOne(vs)

        if allow_unscheduled and unsched_vars:
            model.Minimize(sum(unsched_vars.values()))

        print(f"--- Solving Elective Model ({len(variables)} variables) ---")
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit)
        solver.parameters.log_search_progress = False
        status = solver.Solve(model)

        elective_schedule = []
        updated_occ = {'faculty': pre_fac, 'room': pre_room}
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            print("  - SOLVED Elective Model")
            if allow_unscheduled and unsched_vars:
                n_unsched = sum(int(solver.Value(v)) for v in unsched_vars.values())
                print(f"  - Unscheduled electives (minimized): {n_unsched}")
            for key, var in variables.items():
                if solver.Value(var) == 1:
                    g_name, session_id, f_id, r_id, t_start = key
                    course_id = session_id.split('_S')[0]
                    elective_schedule.append((f_id, course_id, t_start, r_id, g_name))
                    duration = course_details_map.get(course_id, {}).get('duration', 1)
                    current = t_start
                    start_day = str(t_start).split('_', 1)[0]
                    for _ in range(duration):
                        if (not current) or (str(current).split('_', 1)[0] != start_day):
                            break
                        updated_occ['faculty'][f_id].add(current)
                        updated_occ['room'][r_id].add(current)
                        current = self.next_slot_map.get(current)
            return elective_schedule, updated_occ, True
        else:
            print("  - FAILED to solve the elective model.")
            return elective_schedule, updated_occ, False

  



    


    # Optional helper: consistent tuple list if needed by callers
    @staticmethod
    def format_schedule(schedule_list):
        # Already in (Faculty ID, Course ID, Time Slot, Room ID, Batch/Group ID) tuple form
        return schedule_list
