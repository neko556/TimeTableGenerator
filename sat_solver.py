import pandas as pd
from datetime import datetime, timedelta

from collections import defaultdict
from preprocessor import load_data
from ortools.sat.python import cp_model
from collections import defaultdict
import pandas as pd


class TimetableSATModel:
    def __init__(self, data, batches, batch_courses, time_slot_map, next_slot_map):
        self.data = data
        self.batches = batches
        self.batch_courses = batch_courses
        self.time_slot_map = time_slot_map
        self.next_slot_map = next_slot_map
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
        self.variables = {}

    def build_model(self):
        print("Building OR-Tools CP-SAT model with hard constraints...")
        
        # --- Pre-process data for efficient lookups ---
        faculty_availability = defaultdict(set)
        for _, row in self.data['faculty_availability'].iterrows():
            if 'available' in row.get('availability_type', '').lower():
                slot = f"{row['day_of_week']}_{row['time_slot_start']}-{row['time_slot_end']}"
                if slot in self.time_slot_map:
                    faculty_availability[row['faculty_id']].add(slot)

        room_availability = defaultdict(set)
        for _, row in self.data['room_availability'].iterrows():
            if 'available' in row.get('availability_status', '').lower():
                # This logic now correctly generates all 1-hour slots within a larger availability window
                day = row['day_of_week']
                start_time = pd.to_datetime(row['time_slot_start']).time()
                end_time = pd.to_datetime(row['time_slot_end']).time()
                for slot_label, slot_id in self.time_slot_map.items():
                    if slot_label.startswith(day):
                        slot_start_str = slot_label.split('_')[1].split('-')[0]
                        slot_start_time = pd.to_datetime(slot_start_str).time()
                        if start_time <= slot_start_time < end_time:
                            room_availability[row['room_id']].add(slot_label)

        course_details = {}
        for _, course in self.data['courses'].iterrows():
            course_details[course['course_id']] = {
                'duration': int(course.get('duration_hours', 1)),
                'is_lab': 'lab' in course.get('course_type', '').lower()
            }

        expertise_map = defaultdict(list)
        for _, row in self.data['faculty_expertise'].iterrows():
            expertise_map[row['course_id']].append(row['faculty_id'])

        # --- Create Variables with Diagnostics ---
        print("\n--- Generating Possible Assignments (Variables) ---")
        total_vars_created = 0
        
        for b_id, courses in self.batch_courses.items():
            for c_id in courses:
                vars_for_this_course = 0
                details = course_details.get(c_id, {'duration': 1, 'is_lab': False})
                duration = details['duration']
                is_lab = details['is_lab']
                
                for f_id in expertise_map.get(c_id, []):
                    for _, room_row in self.data['rooms'].iterrows():
                        r_id = room_row['room_id']
                        room_type = room_row.get('room_type', '').lower()
                        
                        if (is_lab and 'lab' not in room_type) or (not is_lab and 'lab' in room_type):
                            continue

                        for t_start in self.time_slot_map:
                            is_fully_available = True
                            required_slots = [t_start]
                            current_slot = t_start
                            
                            for _ in range(duration - 1):
                                next_slot = self.next_slot_map.get(current_slot)
                                if not next_slot:
                                    is_fully_available = False
                                    break
                                required_slots.append(next_slot)
                                current_slot = next_slot

                            if not is_fully_available:
                                continue

                            for slot in required_slots:
                                if slot not in faculty_availability.get(f_id, set()) or slot not in room_availability.get(r_id, set()):
                                    is_fully_available = False
                                    break
                            
                            if is_fully_available:
                                key = (b_id, c_id, f_id, r_id, t_start)
                                self.variables[key] = self.model.NewBoolVar(f'assign_{b_id}_{c_id}_{f_id}_{r_id}_{t_start}')
                                vars_for_this_course += 1
                
                print(f"  - For Course '{c_id}' in Batch '{b_id}': Found {vars_for_this_course} possible assignment slots.")
                if vars_for_this_course == 0:
                    print(f"    - 🔴 FATAL: No valid time/room/faculty combination found for this course. Check data for conflicts.")
                total_vars_created += vars_for_this_course

        print(f"Total variables created: {total_vars_created}\n")
        if total_vars_created == 0:
             print("No variables were created at all. The model will be INFEASIBLE. Check your data files.")
             return # Stop building if no variables were created

        # --- Add Core Constraints ---
        for b_id, courses in self.batch_courses.items():
            for c_id in courses:
                possible_assignments = [var for key, var in self.variables.items() if key[0] == b_id and key[1] == c_id]
                # Only add constraint if there are options to choose from
                if possible_assignments:
                    self.model.AddExactlyOne(possible_assignments)

        occupancy = defaultdict(list)
        for (b_id, c_id, f_id, r_id, t_start), var in self.variables.items():
            duration = course_details[c_id]['duration']
            current_slot = t_start
            for _ in range(duration):
                if current_slot:
                    occupancy[('batch', b_id, current_slot)].append(var)
                    occupancy[('faculty', f_id, current_slot)].append(var)
                    occupancy[('room', r_id, current_slot)].append(var)
                    current_slot = self.next_slot_map.get(current_slot)
        
        for key, vars_in_slot in occupancy.items():
            if len(vars_in_slot) > 1:
                self.model.AddAtMostOne(vars_in_slot)

        for (b_id, c_id, f_id, r_id, t_start), var in self.variables.items():
            batch_size = len(self.batches[b_id])
            room_capacity = self.data['rooms'].loc[self.data['rooms']['room_id'] == r_id, 'capacity'].iloc[0]
            if batch_size > room_capacity:
                self.model.Add(var == 0)

    def solve(self):
        print("Solving with CP-SAT...")
        self.solver.parameters.log_search_progress = True
        status = self.solver.Solve(self.model)
        
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            print("✅ SAT solution found!")
            solution = []
            for (b_id, c_id, f_id, r_id, t_slot), var in self.variables.items():
                if self.solver.Value(var) == 1:
                    solution.append((f_id, c_id, t_slot, r_id, b_id))
            return solution
        else:
            print("❌ No solution found by the SAT solver.")
            return None