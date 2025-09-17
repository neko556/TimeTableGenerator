import pandas as pd
from preprocessor import run_preprocessing_pipeline, build_elective_groups_from_data
from sat_solver import BatchTimetableSATModel
from time_slots import generate_time_slots

# Config
ELECTIVE_CREDITS = 3
ELECTIVES_TAKEN = 1
STRICT_CORE = True
E_GLOBAL = 5  # shared elective windows

def main():
    """
    Two-phase CP-SAT timetabling:
      - Phase 1: cores only + GLOBAL elective windows z_t (shared across all batches)
      - Phase 2: electives only inside those windows, with faculty/room no-overlap
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
    for g, batches in group_to_batches.items():
        sets = [core_reserved.get(b, set()) for b in batches]
        inter = set.intersection(*sets) if sets else set()
        allowed = inter if inter else set().union(*sets)
        print(f"[elective-domain] {g}: batches={batches}, allowed={len(allowed)}")

    # --- Phase 2: electives inside reserved windows ---
    final_schedule_list = list(core_schedule)
    intended_elec = sum(len(v) for v in elective_group_sessions.values())
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
        else:
            print("⚠ Elective scheduling returned no assignments; check [elective-domain] and [elective-zero] logs.")

    # --- Display combined timetable ---
    if not final_schedule_list:
        print("\n❌ No schedule could be generated.")
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
    print(timetable_df.to_string())

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

if __name__ == "__main__":
    main()
