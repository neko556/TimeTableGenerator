import math
import statistics as stats
import pandas as pd
from collections import defaultdict, Counter

from preprocessor import run_preprocessing_pipeline, build_elective_groups_from_data
from sat_solver import BatchTimetableSATModel
from time_slots import generate_time_slots
from ga_solver import GeneticAlgorithmTimetable
from tabu_search import TabuSearchTimetable
import traceback
import json
from constraints_io import load_constraints
GA_AVAILABLE = False
TABU_AVAILABLE = False

# Optional metaheuristics


# Toggles for post-optimization stages
RUN_GA = True
RUN_TABU = True

# Config defaults (data-driven sizing is used where possible)
ELECTIVE_CREDITS = 3
ELECTIVES_TAKEN = 1
STRICT_CORE = True

import pandas as pd

def display_all_timetables(core_schedule, elec_schedule, core_batches, elective_groups):
    """
    Consolidates all display logic into a single, comprehensive function.
    
    1. Builds a clean DataFrame from the core and elective schedules.
    2. Prints a master timetable of all assignments.
    3. Prints individual timetables for each faculty, room, and batch/group.
    4. Provides an interactive prompt to look up the timetable for any student.
    """
    
    # 1. Combine schedule data and create the main DataFrame
    full_schedule_data = core_schedule + elec_schedule
    if not full_schedule_data:
        print("\n[info] No assignments were made in the final schedule.")
        return

    try:
        df = pd.DataFrame(full_schedule_data, columns=[
            'Faculty ID', 'Course ID', 'Time Slot', 'Room ID', 'Batch/Group ID'
        ])
    except ValueError as e:
        print(f"\n[error] Failed to create timetable DataFrame: {e}")
        return

    # 2. Helper function to parse 'Time Slot' into sortable columns
    def parse_slot(slot_str):
        try:
            day, time = slot_str.split('_', 1)
            return day, time
        except (ValueError, AttributeError):
            return "Unknown", "Unknown"

    df[['Day', 'Time']] = df['Time Slot'].apply(lambda x: pd.Series(parse_slot(x)))
    
    # Define a consistent order for days of the week
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    df['Day'] = pd.Categorical(df['Day'], categories=day_order, ordered=True)

    # --- 3. Master Timetable ---
    print("\n--- ✅ Master Timetable (All Assignments) ---")
    master_df = df.sort_values(by=['Day', 'Time', 'Room ID', 'Faculty ID']).reset_index(drop=True)
    print(master_df[['Day', 'Time', 'Course ID', 'Room ID', 'Faculty ID', 'Batch/Group ID']].to_string(index=False))

    # --- 4. Faculty Timetables ---
    print("\n--- ✅ Faculty Timetables (All) ---")
    for fac_id in sorted(df['Faculty ID'].dropna().unique()):
        fac_df = df[df['Faculty ID'] == fac_id].sort_values(by=['Day', 'Time']).reset_index(drop=True)
        print(f"\n--- Timetable for Faculty: {fac_id} ---")
        print(fac_df[['Day', 'Time', 'Course ID', 'Room ID', 'Batch/Group ID']].to_string(index=False))

    # --- 5. Room Timetables ---
    print("\n--- ✅ Room Timetables (All) ---")
    for room_id in sorted(df['Room ID'].dropna().unique()):
        room_df = df[df['Room ID'] == room_id].sort_values(by=['Day', 'Time']).reset_index(drop=True)
        print(f"\n--- Timetable for Room: {room_id} ---")
        print(room_df[['Day', 'Time', 'Course ID', 'Faculty ID', 'Batch/Group ID']].to_string(index=False))

    # --- 6. Batch/Group Timetables ---
    print("\n--- ✅ Batch/Group Timetables (All) ---")
    for batch_id in sorted(df['Batch/Group ID'].dropna().unique()):
        batch_df = df[df['Batch/Group ID'] == batch_id].sort_values(by=['Day', 'Time']).reset_index(drop=True)
        print(f"\n--- Timetable for Batch/Group: {batch_id} ---")
        print(batch_df[['Day', 'Time', 'Course ID', 'Faculty ID', 'Room ID']].to_string(index=False))

    # --- 7. Interactive Student Timetable Lookup ---
    print("\n--- ✅ Student Timetable Lookup ---")
    stud_to_elective_groups = {}
    for g, members in elective_groups.items():
        for s in members:
            stud_to_elective_groups.setdefault(s, []).append(g)

    while True:
        print("\n" + "=" * 50)
        student_id = input("Enter Student ID to view timetable (or type 'exit' to quit): ")
        if student_id.strip().lower() == 'exit':
            break

        core_batch = next((name for name, students in core_batches.items() if student_id in students), None)
        groups = stud_to_elective_groups.get(student_id, [])
        
        selection_ids = [core_batch] if core_batch else []
        selection_ids.extend(groups)

        if not selection_ids:
            print(f"Student '{student_id}' not found in any core batch or elective group.")
            continue

        student_schedule_df = df[df['Batch/Group ID'].isin(selection_ids)].sort_values(by=['Day', 'Time'])
        
        print(f"\n--- Timetable for Student: {student_id} ---")
        if student_schedule_df.empty:
            print("No classes found for this student in the final schedule.")
        else:
            print(student_schedule_df[['Day', 'Time', 'Course ID', 'Faculty ID', 'Room ID']].to_string(index=False))


    


def compute_e_global_from_data(data, elective_ids=None, availability_by_slot=None, buffer_ratio=0.15, availability_factor=0.6):
    """
    Compute E_GLOBAL using a capacity formula:
      E_GLOBAL = ceil(D / K_eff) * (1 + buffer_ratio)
    where D is total elective session demand, and K_eff is per-window parallel capacity.
    Labs count as 1 session; theory uses credits sessions.
    """
    courses = data['courses']
    rooms = data['rooms']
    expertise = data['faculty_expertise']

    elec = courses[courses['is_elective'] == True].copy()
    if elective_ids:
        elec_ids_set = set(map(str, elective_ids))
        elec = elec[elec['course_id'].astype(str).isin(elec_ids_set)].copy()

    def is_lab_row(row): return 'lab' in str(row.get('course_type', '')).lower()
    def sessions_needed(row):
        cr = pd.to_numeric(row.get('credits'), errors='coerce')
        cr = int(cr) if pd.notna(cr) else ELECTIVE_CREDITS
        return 1 if is_lab_row(row) else max(1, cr)

    D = int(elec.apply(sessions_needed, axis=1).sum())

    elec_ids = set(elec['course_id'].astype(str))
    expert_fac = expertise[expertise['course_id'].astype(str).isin(elec_ids)]['faculty_id'].unique()
    F_total = int(len(expert_fac))
    R_total = int(len(rooms['room_id'].unique()))

    if availability_by_slot:
        caps = []
        for _, caps_dict in availability_by_slot.items():
            F_t = int(caps_dict.get('faculty_elective_available', F_total))
            R_t = int(caps_dict.get('rooms_ok_available', R_total))
            caps.append(min(F_t, R_t))
        K_eff = max(1, int(stats.median(caps))) if caps else max(1, min(F_total, R_total))
    else:
        K_eff = max(1, int(min(F_total, R_total) * float(availability_factor)))

    E = int(math.ceil(D / max(1, K_eff)))
    E = int(math.ceil(E * (1.0 + float(buffer_ratio))))
    return max(1, E), {'D': D, 'K_eff': K_eff}


# ---- Memetic helpers (mix cores + electives safely at session-level) ----

def is_lab_course(courses_df, course_id):
    row = courses_df.loc[courses_df['course_id'] == course_id]
    ctype = str(row['course_type'].iloc[0]).lower() if len(row) else ''
    return 'lab' in ctype

def student_gap_contrib_sid(assignments_sid, sid_to_course, course_student_map):
    # approximate per-session contribution to student gaps (higher = worse)
    # assignments_sid: list[(f,sid,t,r)]
    day_hour = {}
    for f, sid, t, r in assignments_sid:
        c = sid_to_course.get(sid, sid)
        d = str(t).split('_', 1)[0]; h = int(str(t).split('_', 1)[1].split(':')[0])
        for sid_stu in course_student_map.get(c, []):
            day_hour.setdefault(sid_stu, {}).setdefault(d, []).append(h)
    contrib = {}
    for f, sid, t, r in assignments_sid:
        c = sid_to_course.get(sid, sid)
        d = str(t).split('_', 1)[0]; h = int(str(t).split('_', 1)[1].split(':')[0])
        worst = 0
        for sid_stu in course_student_map.get(c, []):
            hours = list(day_hour.get(sid_stu, {}).get(d, []))
            if h not in hours: continue
            hours.sort()
            span = (hours[-1] - hours[0] + 1) - len(hours)
            worst = max(worst, span)
        contrib[sid] = max(contrib.get(sid, 0), worst)
    return contrib

def build_allowed_windows_sid(time_slot_keys, core_reserved, elective_group_sessions, allowed_slots_per_group,
                              core_sids, sid_to_group):
    all_slots = set(time_slot_keys)
    z_union = set()
    for _, w in core_reserved.items():
        z_union |= set(w)
    allowed_by_sid = {}
    # electives by group
    for sid, g in sid_to_group.items():
        allowed_by_sid[sid] = set(allowed_slots_per_group.get(g, set()))
    # cores in non-elective windows
    for sid in core_sids:
        allowed_by_sid.setdefault(sid, set()).update(all_slots - z_union)
    return allowed_by_sid, all_slots, z_union


def main():
    """
    Two-phase CP-SAT timetabling:
      - Phase 1: cores only + GLOBAL elective windows z_t (shared across all batches)
      - Phase 2: electives inside those windows, with faculty/room no-overlap
      - Phase 3: memetic hybrid (GA + Tabu) over a small mixed session-level scope (cores+electives),
                with cores restricted to non-elective windows and electives to reserved windows
    """
    # --- Setup ---
    time_slots, time_slot_map, next_slot_map = generate_time_slots()

    # --- Preprocessing ---
    result = run_preprocessing_pipeline()
    if len(result) == 5:
        data, core_batches, core_batch_sessions, elective_groups, elective_group_sessions = result
    else:
        data, core_batches, core_batch_sessions = result
        elective_groups, elective_group_sessions = {}, {}

    # Fallback if electives missing or empty
    if (not elective_groups) or (sum(len(v) for v in elective_group_sessions.values()) == 0):
        print("[info] Building electives from data fallback...")
        elective_groups, elective_group_sessions = build_elective_groups_from_data(
            data, elective_credits=ELECTIVE_CREDITS
        )

    print(f"[sanity] Elective groups: {len(elective_groups)}, elective sessions: {sum(len(v) for v in elective_group_sessions.values())}")

    # --- Core sanity ---
    total_core_sessions = sum(len(s) for s in core_batch_sessions.values())
    print(f"Core batches: {len(core_batches)}, core sessions: {total_core_sessions}")
    for b, sess in list(core_batch_sessions.items())[:5]:
        print(f"  {b}: {len(sess)} sessions -> {sess[:8]}")
    if total_core_sessions == 0:
        print("No core sessions generated; fix Basket_Courses/IDs before solving.")
        return
    constraints = load_constraints("constraints.json")
    hard_cfg = constraints.get("hard", {})
    soft_cfg = constraints.get("soft", {})


    # --- Compute E_GLOBAL from data using the capacity-based formula ---
    elective_course_ids_from_groups = set()
    for g, sess_list in elective_group_sessions.items():
        for s_id in sess_list:
            elective_course_ids_from_groups.add(str(s_id).split('_S')[0])

    E_GLOBAL, info = compute_e_global_from_data(
        data=data,
        elective_ids=elective_course_ids_from_groups if elective_course_ids_from_groups else None,
        availability_by_slot=None,
        buffer_ratio=0.15,
        availability_factor=0.6
    )
    print(f"[e_global] Computed E_GLOBAL={E_GLOBAL} using D={info['D']} and K_eff={info['K_eff']}")

    # --- Phase 1: cores with GLOBAL elective windows (z_t) ---
    print("\n--- Scheduling All Core Course Sessions ---")
    core_solver = BatchTimetableSATModel(
        data=data,
        batches=core_batches,
        batch_sessions=core_batch_sessions,
        time_slot_map=time_slot_map,
        next_slot_map=next_slot_map,
        occupied_slots=None,
        allow_unscheduled=not STRICT_CORE
    )
    core_schedule, occupied_slots, ok, core_reserved = core_solver.solve(
        time_limit=300,
        global_elective_windows=E_GLOBAL,
        hard_cfg=hard_cfg,
        soft_cfg=soft_cfg,
        use_assumptions=False
    )
    if not ok or not core_schedule:
        print("\n❌ CRITICAL ERROR: Could not schedule the core courses or schedule is empty.")
        print("   - Suggestions: Check resources/availability and curriculum size.")
        return

    # --- Reservations summary ---
    if core_reserved:
        any_b = next(iter(core_reserved))
        print("Global elective windows picked:", sorted(list(core_reserved[any_b]))[:10])

    # --- Diagnostics: allowed slots per group (intersection fallback to union) ---
    group_to_batches = {
        g: [b for b, roster in core_batches.items() if any(s in roster for s in students)]
        for g, students in elective_groups.items()
    }
    allowed_slots_per_group = {}
    for g, batches in group_to_batches.items():
        sets = [core_reserved.get(b, set()) for b in batches]
        inter = set.intersection(*sets) if sets else set()
        allowed = inter if inter else set().union(*sets)
        allowed_slots_per_group[g] = allowed
        print(f"[elective-domain] {g}: batches={batches}, allowed={len(allowed)}")

    # --- Phase 2: electives inside reserved windows ---
    final_schedule_list = list(core_schedule)
    intended_elec = sum(len(v) for v in elective_group_sessions.values())
    elective_rows = []
    if intended_elec == 0:
        print("[warn] No elective sessions available; skipping elective phase.")
    else:
        print("\n--- Scheduling Elective Sessions (Phase 2) ---")
        elec_schedule, occupied_slots2, ok2 = core_solver.solve_electives(
        elective_groups=elective_groups,
        elective_group_sessions=elective_group_sessions,
        core_reserved=core_reserved,
        core_batches=core_batches,
        occupied_slots=occupied_slots,
        time_limit=90,
        allow_unscheduled=True,
        hard_cfg=hard_cfg,
        soft_cfg=soft_cfg
    )
        if ok2 and elec_schedule:
            final_schedule_list += elec_schedule
            elective_rows = list(elec_schedule)
        else:
            print("⚠ Elective scheduling returned no assignments; check [elective-domain] and [elective-zero] logs.")

    # --- Build session IDs (sid) for the current schedule ---
    # Cores: CORE::{batch}::{course}::{k}
    core_sid_rows = []
    core_counters = defaultdict(int)
    for (f, c, t, r, b) in core_schedule:
        core_counters[(b, c)] += 1
        k = core_counters[(b, c)]
        sid = f"CORE::{b}::{c}::{k}"
        core_sid_rows.append((sid, f, c, t, r, b))

    # Electives: ELEC::{group}::{course}::{k}
    elec_sid_rows = []
    elec_counters = defaultdict(int)
    for (f, c, t, r, g) in elective_rows:
        elec_counters[(g, c)] += 1
        k = elec_counters[(g, c)]
        sid = f"ELEC::{g}::{c}::{k}"
        elec_sid_rows.append((sid, f, c, t, r, g))

    # sid maps
    sid_to_course = {}
    sid_to_group = {}
    for sid, f, c, t, r, b in core_sid_rows:
        sid_to_course[sid] = c
    for sid, f, c, t, r, g in elec_sid_rows:
        sid_to_course[sid] = c
        sid_to_group[sid] = g

    # --- Phase 3: Memetic hybrid (session-level) ---
    allowed_by_sid, all_slots_set, z_union = build_allowed_windows_sid(
        time_slot_map.keys(), core_reserved, elective_group_sessions, allowed_slots_per_group,
        core_sids=[sid for sid, *_ in core_sid_rows],
        sid_to_group=sid_to_group
    )

    # Current sid assignments
    core_sid_assignments = [(f, sid, t, r) for (sid, f, c, t, r, b) in core_sid_rows]
    elec_sid_assignments = [(f, sid, t, r) for (sid, f, c, t, r, g) in elec_sid_rows]
    current_all_sid = core_sid_assignments + elec_sid_assignments

    # Data for hotspot selection
    course_student_map = data['student_choices'].groupby('chosen_course_id')['student_id'].apply(list).to_dict()
    sid_contrib = student_gap_contrib_sid(current_all_sid, sid_to_course, course_student_map)

    # Select movable sids: top theory cores by contribution + all electives
    movable_core_sids = []
    for (f, sid, t, r) in core_sid_assignments:
        c = sid_to_course.get(sid, sid)
        if not is_lab_course(data['courses'], c):
            movable_core_sids.append((sid, sid_contrib.get(sid, 0)))
    movable_core_sids.sort(key=lambda x: x[1], reverse=True)
    movable_core_sids = [sid for sid, _ in movable_core_sids[:16]]
    movable_elec_sids = [sid for (f, sid, t, r) in elec_sid_assignments]
    movables_sid = sorted(set(movable_core_sids + movable_elec_sids))

    if movables_sid:
        # Seed and fixed
        seed_sid = {(f, sid, t, r): True for (f, sid, t, r) in current_all_sid if sid in movables_sid}
        fixed_sid = [(f, sid, t, r) for (f, sid, t, r) in current_all_sid if sid not in movables_sid]

        # Domain guard: ensure seed slot is allowed for each sid
        for (f, sid, t, r) in list(seed_sid.keys()):
            allowed_by_sid.setdefault(sid, set()).add(t)
        empty_sids = [sid for sid in movables_sid if not allowed_by_sid.get(sid)]
        if empty_sids:
            print(f"[memetic][warn] sids with empty domain: {len(empty_sids)} -> auto-adding seed slots")

        # Seed sanity before GA
        if RUN_GA and GA_AVAILABLE and seed_sid:
            try:
                ga_dbg = GeneticAlgorithmTimetable(
                    data=data,
                    next_slot_map=next_slot_map,
                    population_size=2, generations=1,
                    mutation_rate=0.0, crossover_rate=0.0,
                    sid_scope=movables_sid,
                    sid_to_course=sid_to_course,
                    fixed_assignments=fixed_sid,
                    allowed_slots_by_sid=allowed_by_sid,
                    seed_schedule=seed_sid,
                )
                seed_ind = {k: True for k in seed_sid.keys()}
                v = ga_dbg.hard_constraint_violations(seed_ind)
                missing = len(movables_sid) - len({k[1] for k in seed_ind.keys()})
                print(f"[memetic][seed] conflicts={v}, missing={missing}")
            except Exception as e:
                print(f"[warn] GA (memetic sid) seed check failed: {e}")

        # GA exploration (sid-scope)
        if RUN_GA and GA_AVAILABLE and seed_sid:
            try:
                ga = GeneticAlgorithmTimetable(
                    data=data,
                    next_slot_map=next_slot_map,
                    population_size=24,
                    generations=10,
                    mutation_rate=0.35,
                    crossover_rate=0.8,
                    sid_scope=movables_sid,
                    sid_to_course=sid_to_course,
                    fixed_assignments=fixed_sid,
                    allowed_slots_by_sid=allowed_by_sid,
                    seed_schedule=seed_sid
                )
                ga.initialize_population([seed_sid])
                best = ga.run()
                if isinstance(best, dict) and len(best) > 0:
                    ga_solution = list(best.keys())
                    current_all_sid = fixed_sid + ga_solution
            except Exception as e:
                print(f"[warn] GA (memetic sid) skipped due to error: {e}")

        # Tabu intensification (sid-scope)
        if RUN_TABU and TABU_AVAILABLE:
            try:
                movable_dict = {(f, sid, t, r): True
                                for (f, sid, t, r) in current_all_sid
                                if sid in movables_sid}
                tabu = TabuSearchTimetable(
                    data=data,
                    next_slot_map=next_slot_map,
                    tabu_tenure=10,
                    max_iterations=50,
                    sid_scope=set(movables_sid),
                    sid_to_course=sid_to_course,
                    allowed_slots_by_sid=allowed_by_sid,
                    fixed_assignments=[(f, sid, t, r)
                                    for (f, sid, t, r) in current_all_sid
                                    if sid not in movables_sid]
                )
                improved = tabu.run(movable_dict)
                if isinstance(improved, dict) and len(improved) > 0:
                    # Merge fixed + improved movable
                    current_all_sid = [(f, sid, t, r) for (f, sid, t, r) in current_all_sid if sid not in movables_sid]
                    current_all_sid += list(improved.keys())
            except Exception as e:
        
                print("[warn] Tabu (memetic sid) skipped:")
                print(traceback.format_exc())
        # Rebuild final schedule with original labels
        final_schedule_list = []
        core_sid_to_label = {sid: b for (sid, f, c, t, r, b) in core_sid_rows}
        elec_sid_to_label = {sid: g for (sid, f, c, t, r, g) in elec_sid_rows}
        for (f, sid, t, r) in current_all_sid:
            c = sid_to_course.get(sid, sid)
            if sid in core_sid_to_label:
                b = core_sid_to_label[sid]
                final_schedule_list.append((f, c, t, r, b))
            elif sid in elec_sid_to_label:
                g = elec_sid_to_label[sid]
                final_schedule_list.append((f, c, t, r, g))
            else:
                final_schedule_list.append((f, c, t, r, f"SID_{sid}"))
    else:
        print("[memetic] No movable sids selected; skipping memetic pass.")

    # --- Display combined timetable ---
    if not final_schedule_list:
        print("\n❌ No schedule could be generated.")
        return

    
    
    display_all_timetables(core_schedule, elec_schedule, core_batches, elective_groups)

   

   


if __name__ == "__main__":
    main()