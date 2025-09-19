import pandas as pd
from collections import defaultdict
from ortools.sat.python import cp_model

class BatchTimetableSATModel:
    def __init__(self, data, batches, batch_sessions, time_slot_map, **kwargs):
        self.data = data
        self.batches = batches
        self.batch_sessions = batch_sessions
        self.time_slot_map = time_slot_map

    def _get_course_details_map(self):
        """Builds a map from course_id to its details like duration and type."""
        details = {}
        for _, course in self.data.get('courses', pd.DataFrame()).iterrows():
            details[course['course_id']] = {
                'duration': int(course.get('duration_hours', 1)),
                'is_lab': 'lab' in str(course.get('course_type', '')).lower()
            }
        return details

    def solve(self, time_limit=180, **kwargs):
        """
        Generates the core timetable using a direct and robust interval model.
        This model explicitly creates assignments and enforces their duration.
        """
        model = cp_model.CpModel()
        
        # --- 1. Prepare Data ---
        course_details_map = self._get_course_details_map()
       
        all_rooms_df = self.data['rooms']
        lab_rooms = set(all_rooms_df[all_rooms_df['room_type'] == 'Lab']['room_id'])
        theory_rooms = set(all_rooms_df[all_rooms_df['room_type'] != 'Lab']['room_id'])
        
        # Consistent, sorted time slots are crucial
        slot_keys = sorted(self.time_slot_map.keys())
        num_slots = len(slot_keys)

        # --- 2. Build All Valid, Pre-checked Assignments ---
        assignments = []
        sessions_to_cover = defaultdict(list)
        
        # Resource lists for the NoOverlap constraint
        faculty_intervals = defaultdict(list)
        room_intervals = defaultdict(list)
        batch_intervals = defaultdict(list)
        sessions_to_cover = defaultdict(list)
        assignments = []

        for b_id, sessions in self.batch_sessions.items():
            for session_id in sessions:
                course_id = session_id.split('_S')[0]
                details = course_details_map.get(course_id, {})
                duration = details.get('duration', 1)
                is_lab = details.get('is_lab', False)

               
                # Get valid faculty and rooms for this course
                possible_faculties = self.data['faculty_expertise'][
                    self.data['faculty_expertise']['course_id'] == course_id
                ]['faculty_id'].tolist()
                possible_rooms = lab_rooms if is_lab else theory_rooms

                # Create a single optional interval per valid (faculty, room, start) with the TRUE duration
                for f_id in possible_faculties:
                    for r_id in possible_rooms:
                        for i in range(0, num_slots - duration + 1):
                            start_i = i
                            end_i = i + duration

                            # Constraint: do not spill across days
                            start_day = slot_keys[start_i].split('_', 1)[0]
                            end_day = slot_keys[end_i - 1].split('_', 1)[0]
                            if start_day != end_day:
                                continue

                            lit = model.NewBoolVar(f'assign_{b_id}_{session_id}_{f_id}_{r_id}_{start_i}')

                            # CRITICAL: duration is used here (not 1)
                            interval = model.NewOptionalIntervalVar(
                                start_i, duration, end_i, lit,
                                f'ival_{b_id}_{session_id}_{f_id}_{r_id}_{start_i}'
                            )

                           
                            # Add to resource interval lists
                            faculty_intervals[f_id].append(interval)
                            room_intervals[r_id].append(interval)
                            batch_intervals[b_id].append(interval)

                            # Collect literals for "exactly one"
                            sessions_to_cover[(b_id, session_id)].append(lit)

                            # Keep for extraction; store start slot text for display expansion
                            assignments.append({
                                'literal': lit,
                                'faculty_id': f_id,
                                'room_id': r_id,
                                'batch_id': b_id,
                                'course_id': course_id,
                                'start_slot': slot_keys[start_i],
                                'duration': duration
                            })

        # One option must be chosen per session_id
        for task_key, lits in sessions_to_cover.items():
            model.AddExactlyOne(lits)

        # No-Overlap for resources
        for ivals in faculty_intervals.values():
            model.AddNoOverlap(ivals)
        for ivals in room_intervals.values():
            model.AddNoOverlap(ivals)
        for ivals in batch_intervals.values():
            model.AddNoOverlap(ivals)
        

        # --- 4. Solve the Model ---
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit)
        status = solver.Solve(model)

        # --- 5. Extract the Solution ---
        schedule = []
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            print("  - ✅ Model solved.")
            for a in assignments:
                if solver.Value(a['literal']):
                    # Expand every chosen interval into per-slot rows so labs appear as two rows
                    s_idx = slot_keys.index(a['start_slot'])
                    dur = a['duration']
                    for k in range(dur):
                        idx = s_idx + k
                        if idx >= len(slot_keys):
                            break
                        schedule.append((
                            a['faculty_id'],
                            a['course_id'],
                            slot_keys[idx],     # expanded atomic slot
                            a['room_id'],
                            a['batch_id']
                        ))
            return schedule, {}, True, {}
        else:
            print("  - ❌ No solution.")
            return [], {}, False, {}



    def solve_electives(self, elective_groups, elective_group_sessions, time_limit=120, **kwargs):
        """
        Elective timetable using the same interval-based modeling pattern as core.

        - One OptionalIntervalVar per valid (faculty, room, start) with true duration from Courses.csv.
        - AddExactlyOne per session_id ensures a single, contiguous block is picked.
        - NoOverlap applied to faculty, rooms, and group-level intervals.
        - Extraction expands each chosen multi-hour interval into atomic slots to keep the downstream display consistent.
        """
        model = cp_model.CpModel()

        # --- 1) Data prep: details, rooms, slots ---
        course_details_map = self._get_course_details_map()  # {'CRSxxx': {'duration': h, 'is_lab': bool}}
        all_rooms_df = self.data['rooms']
        lab_rooms = set(all_rooms_df[all_rooms_df['room_type'] == 'Lab']['room_id'])
        theory_rooms = set(all_rooms_df[all_rooms_df['room_type'] != 'Lab']['room_id'])

        slot_keys = sorted(self.time_slot_map.keys())
        num_slots = len(slot_keys)

        # --- 2) Build all valid assignment options ---
        assignments = []
        sessions_to_cover = defaultdict(list)

        faculty_intervals = defaultdict(list)
        room_intervals = defaultdict(list)
        group_intervals = defaultdict(list)

        # elective_group_sessions: {group_name: [CRSxxx_S1, ...]}
        for g_name, sessions in elective_group_sessions.items():
            for session_id in sessions:
                course_id = session_id.split('_S')[0]
                details = course_details_map.get(course_id, {})
                duration = details.get('duration', 1)
                is_lab = details.get('is_lab', False)

                # Faculty expertise domain for the course
                possible_faculties = self.data['faculty_expertise'][
                    self.data['faculty_expertise']['course_id'] == course_id
                ]['faculty_id'].tolist()
                possible_rooms = lab_rooms if is_lab else theory_rooms

                # Create a single optional interval per (faculty, room, start)
                for f_id in possible_faculties:
                    for r_id in possible_rooms:
                        for i in range(0, num_slots - duration + 1):
                            start_i = i
                            end_i = i + duration

                            # Do not spill a multi-hour block across day boundaries
                            start_day = slot_keys[start_i].split('_', 1)[0]
                            end_day = slot_keys[end_i - 1].split('_', 1)[0]
                            if start_day != end_day:
                                continue

                            # One literal per multi-hour option
                            lit = model.NewBoolVar(f'assign_{g_name}_{session_id}_{f_id}_{r_id}_{start_i}')

                            # The interval captures contiguity and duration in one construct
                            interval = model.NewOptionalIntervalVar(
                                start_i, duration, end_i, lit,
                                f'ival_{g_name}_{session_id}_{f_id}_{r_id}_{start_i}'
                            )

                            # Add to resource interval pools and session coverage
                            faculty_intervals[f_id].append(interval)
                            room_intervals[r_id].append(interval)
                            group_intervals[g_name].append(interval)
                            sessions_to_cover[(g_name, session_id)].append(lit)

                            # Keep for extraction; store start slot text
                            assignments.append({
                                'literal': lit,
                                'faculty_id': f_id,
                                'room_id': r_id,
                                'group_id': g_name,
                                'course_id': course_id,
                                'start_slot': slot_keys[start_i],
                                'duration': duration
                            })

        # --- 3) Constraints: coverage and NoOverlap ---
        # Each elective session must be assigned exactly once
        for task_key, lits in sessions_to_cover.items():
            model.AddExactlyOne(lits)

        # No-Overlap for resources
        for ivals in faculty_intervals.values():
            model.AddNoOverlap(ivals)
        for ivals in room_intervals.values():
            model.AddNoOverlap(ivals)
        for ivals in group_intervals.values():
            model.AddNoOverlap(ivals)

        # --- 4) Solve ---
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit)
        status = solver.Solve(model)

        # --- 5) Extract and expand into atomic slots for display ---
        schedule = []
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            print("  - ✅ Elective model solved.")
            for a in assignments:
                if solver.Value(a['literal']):
                    s_idx = slot_keys.index(a['start_slot'])
                    dur = a['duration']
                    # Expand chosen interval into per-slot rows
                    for k in range(dur):
                        idx = s_idx + k
                        if idx >= len(slot_keys):
                            break
                        schedule.append((
                            a['faculty_id'],
                            a['course_id'],
                            slot_keys[idx],     # expanded atomic slot
                            a['room_id'],
                            a['group_id']
                        ))
            # Occupied map placeholder (same signature as core)
            return schedule, {}, True
        else:
            print("  - ❌ No elective solution.")
            return [], {}, False
