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
import warnings
import argparse
import json
import builtins
import sys
import os

warnings.filterwarnings("ignore", category=FutureWarning)

# Optional metaheuristics
try:
    from ga_solver import GeneticAlgorithmTimetable
    GA_AVAILABLE = True
except Exception:
    GA_AVAILABLE = False

try:
    from tabu_search import TabuSearchTimetable
    TABU_AVAILABLE = True
except Exception:
    TABU_AVAILABLE = False

# Toggles for post-optimization stages
RUN_GA = True
RUN_TABU = True

# Config defaults (data-driven sizing is used where possible)
ELECTIVE_CREDITS = 3
ELECTIVES_TAKEN = 1
STRICT_CORE = True

# Global variable to store the last solved result for API access
SOLVED_RESULT = None


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


def set_solved_result(result):
    """Store the solved result globally for API access."""
    global SOLVED_RESULT
    if result is None:
        SOLVED_RESULT = None
        return
    
    # Normalize different input formats
    if isinstance(result, list):
        SOLVED_RESULT = {
            "records": result,
            "core_batches": {},
            "elective_groups": {}
        }
    elif isinstance(result, dict):
        SOLVED_RESULT = {
            "records": result.get("records", result.get("timetable", [])),
            "core_batches": result.get("core_batches", {}),
            "elective_groups": result.get("elective_groups", {})
        }
    else:
        SOLVED_RESULT = None


def get_student_timetable(student_id: str):
    """Returns timetable for the given student_id using the cached SOLVED_RESULT."""
    global SOLVED_RESULT
    if SOLVED_RESULT is None:
        return {"error": "No timetable generated yet. Call /generate first."}

    records = SOLVED_RESULT.get("records", [])
    core_batches = SOLVED_RESULT.get("core_batches", {})
    elective_groups = SOLVED_RESULT.get("elective_groups", {})

    # Find which batch(es) and elective group(s) this student is in
    core_batch = next((name for name, students in core_batches.items() if student_id in students), None)
    student_groups = [g for g, members in elective_groups.items() if student_id in members]

    if not core_batch and not student_groups:
        return {"error": f"Student {student_id} not found in any batch or elective group."}

    selection_ids = []
    if core_batch:
        selection_ids.append(core_batch)
    selection_ids += student_groups

    filtered = [rec for rec in records if rec.get("Batch/Group ID") in selection_ids]

    return {"student_id": student_id, "timetable": filtered}


def main(json_output=False):
    """
    Two-phase CP-SAT timetabling:
      - Phase 1: cores only + GLOBAL elective windows z_t (shared across all batches)
      - Phase 2: electives inside those windows, with faculty/room no-overlap
      - Phase 3: memetic hybrid (GA + Tabu) over a small mixed session-level scope (cores+electives),
                with cores restricted to non-elective windows and electives to reserved windows
    
    If json_output=True, suppresses print output and returns structured data.
    """
    # Suppress prints if producing JSON output
    _orig_print = None
    if json_output:
        _orig_print = builtins.print
        builtins.print = lambda *a, **k: None
    
    try:
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
            if json_output:
                return {"error": "No core sessions generated"}
            return

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
            global_elective_windows=E_GLOBAL
        )
        if not ok or not core_schedule:
            error_msg = "❌ CRITICAL ERROR: Could not schedule the core courses or schedule is empty."
            print(f"\n{error_msg}")
            print("   - Suggestions: Check resources/availability and curriculum size.")
            if json_output:
                return {"error": error_msg}
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
                allow_unscheduled=True
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
                        seed_schedule=seed_sid
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
            error_msg = "❌ No schedule could be generated."
            print(f"\n{error_msg}")
            if json_output:
                return {"error": error_msg}
            return

        print("\n--- ✅ Master Timetable (Core + Electives) ---")
        timetable_df = pd.DataFrame(
            final_schedule_list,
            columns=['Faculty ID', 'Course ID', 'Time Slot', 'Room ID', 'Batch/Group ID']
        )
        mask = timetable_df['Time Slot'].astype('string').str.contains('_', regex=False, na=False)
        timetable_df = timetable_df[mask]
        timetable_df[['Day', 'Time']] = timetable_df['Time Slot'].astype('string').str.split('_', n=1, expand=True)
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        timetable_df['Day'] = pd.Categorical(timetable_df['Day'], categories=day_order, ordered=True)
        timetable_df = timetable_df.sort_values(by=['Day', 'Time', 'Room ID']).reset_index(drop=True)
        
        # If in JSON mode, return records directly
        if json_output:
            records = timetable_df[['Faculty ID','Course ID','Time Slot','Room ID','Batch/Group ID','Day','Time']].to_dict(orient='records')
            return {
                "records": records,
                "core_batches": core_batches,
                "elective_groups": elective_groups
            }
        
        # Otherwise continue with normal display
        print(timetable_df.to_string())

        # --- Faculty timetables (all) ---
        print("\n--- ✅ Faculty Timetables (All) ---")
        fac_day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        for fac_id in sorted(timetable_df['Faculty ID'].dropna().unique()):
            fac_df = timetable_df[timetable_df['Faculty ID'] == fac_id].copy()
            if fac_df.empty:
                continue
            fac_df['Day'] = pd.Categorical(fac_df['Day'], categories=fac_day_order, ordered=True)
            fac_df = fac_df.sort_values(by=['Day', 'Time', 'Room ID']).reset_index(drop=True)
            print(f"\n--- Timetable for Faculty: {fac_id} ---")
            print(fac_df[['Day', 'Time', 'Course ID', 'Room ID', 'Batch/Group ID']].to_string(index=False))

        # --- Student lookup (core batch + elective groups) ---
        stud_to_elective_groups = {}
        for g, members in elective_groups.items():
            for s in members:
                stud_to_elective_groups.setdefault(s, []).append(g)

        while True:
            print("\n" + "=" * 40)
            student_id = input("Enter Student ID to view full timetable (or type 'exit' to quit): ")
            if student_id.lower() == 'exit':
                break
            core_batch = next((name for name, students in core_batches.items() if student_id in students), None)
            groups = stud_to_elective_groups.get(student_id, [])
            selection_ids = [core_batch] if core_batch else []
            selection_ids += groups
            if not selection_ids:
                print(f"Student {student_id} not found in any batch or elective group.")
                continue
            print(f"\n--- Timetable for Student: {student_id} ---")
            student_schedule_df = timetable_df[timetable_df['Batch/Group ID'].isin(selection_ids)]
            if student_schedule_df.empty:
                print("No classes found for this student in the final schedule.")
            else:
                print(student_schedule_df[['Day', 'Time', 'Course ID', 'Faculty ID', 'Room ID']].to_string(index=False))
    
    finally:
        # Restore original print function if it was suppressed
        if _orig_print is not None:
            builtins.print = _orig_print


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", default="hybrid", help="which solver to run")
    parser.add_argument("--json", action="store_true", help="Return JSON timetable & exit (no interactive prompt)")
    args = parser.parse_args()

    # Run solver (use json=True if requested)
    result = main(json_output=args.json)

    # If called in json mode we expect a dict with 'records' etc. Persist a canonical output
    if args.json:
        # Normalize and persist
        if isinstance(result, dict) and "records" in result:
            out = {"timetable": result["records"]}
        elif isinstance(result, list):
            out = {"timetable": result}
            result = {"records": result, "core_batches": {}, "elective_groups": {}}
        else:
            # unexpected structure; try to coerce
            out = {"timetable": []}

        # Save to disk as the canonical persisted file
        os.makedirs("output", exist_ok=True)
        out_path = os.path.join("output", "timetable.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

        # Also set SOLVED_RESULT so other functions in this process can use it
        set_solved_result(result)

        # Print the canonical JSON to stdout (useful for scripting)
        print(json.dumps(out, ensure_ascii=False))
    else:
        # Interactive mode — just run normally (main handled interactive input)
        # But still set SOLVED_RESULT if main returned a result dict (rare for interactive)
        set_solved_result(result)