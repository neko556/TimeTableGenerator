import pandas as pd
from collections import defaultdict
from ortools.sat.python import cp_model
import json

# Import the new generic RuleEngine
from rule_engine import RuleEngine

class BatchTimetableSATModel:
    """
    A CP-SAT model for solving the university timetabling problem, driven by a
    declarative rule engine that reads from a constraints.json file.
    """
    def __init__(self, data, batches, batch_sessions, time_slot_map, next_slot_map, **kwargs):
        self.data = data
        self.batches = batches
        self.batch_sessions = batch_sessions
        self.time_slot_map = time_slot_map
        self.next_slot_map = next_slot_map
        
        # Load dataframes for easy access
        self.courses_df = self.data['courses']
        self.rooms_df = self.data['rooms']
        self.faculty_ids = self.data['faculty']['faculty_id'].unique()
        self.time_slot_keys = list(self.time_slot_map.keys())
        
        # Load external hard and soft constraint configurations from JSON
        try:
            with open('constraints.json', 'r') as f:
                cfg = json.load(f)
            self.hard_config = cfg.get("hard_constraints", {})
            self.soft_config = cfg.get("soft_constraints", {})
            print("[SAT Solver] Successfully loaded constraints from constraints.json")
        except FileNotFoundError:
            print("[warn] constraints.json not found. Proceeding with an empty configuration.")
            self.hard_config, self.soft_config = {}, {}
            
        # Instantiate the RuleEngine to process the loaded configurations
        self.rule_engine = RuleEngine(self.time_slot_map, self.next_slot_map)

    def _day_of(self, t_start):
        """Helper to extract the day from a time slot string."""
        return t_start.split('_')[0]

    def solve(self, time_limit=180):
        """
        Builds and solves the CP-SAT model.
        """
        model = cp_model.CpModel()
        variables = {}
        occupancy = defaultdict(list)
        
        print("\n--- Phase 1: Creating SAT Model Variables ---")
        # Create a variable for every possible valid assignment
        for b_id, sessions in self.batch_sessions.items():
            for session_id in sessions:
                course_id = session_id.split('_S')[0]
                experts = self.data['faculty_expertise'][self.data['faculty_expertise']['course_id'] == course_id]['faculty_id'].tolist()
                
                for f_id in experts:
                    for _, room in self.rooms_df.iterrows():
                        r_id = room['room_id']
                        for t_start in self.time_slot_keys:
                            key = (b_id, session_id, f_id, r_id, t_start)
                            var = model.NewBoolVar(f"assign_{b_id}_{session_id}_{f_id}_{r_id}_{t_start}")
                            variables[key] = var
                            
                            # Populate occupancy lists for core constraints
                            occupancy[("batch", b_id, t_start)].append(var)
                            occupancy[("faculty", f_id, t_start)].append(var)
                            occupancy[("room", r_id, t_start)].append(var)
        
        print(f"Created {len(variables)} potential assignment variables.")

        print("\n--- Phase 2: Adding Core Hard Constraints ---")
        # 1. Each session must be scheduled exactly once
        for b_id, sessions in self.batch_sessions.items():
            for session_id in sessions:
                model.AddExactlyOne(
                    var for key, var in variables.items() if key[0] == b_id and key[1] == session_id
                )

        # 2. No double-booking for any resource at any time
        for key, vars_at_time in occupancy.items():
            model.AddAtMostOne(vars_at_time)
            
        print("Core constraints added (ExactlyOne session, AtMostOne resource).")

        print("\n--- Phase 3: Applying Constraints via Rule Engine ---")
        
        # --- NEW GENERIC RULE APPLICATION ---
        # 1. Apply all hard constraints defined in constraints.json
        self.rule_engine.compile_hard(model, variables, self.hard_config)
        
        # 2. Compile all soft constraints from constraints.json to get penalty terms
        penalty_terms = self.rule_engine.compile_soft(model, variables, self.soft_config)
        
        # 3. Add the soft constraint penalties to the model's objective function
        if penalty_terms:
            total_penalty = model.NewIntVar(0, 100000 * 100, "total_penalty")
            model.Add(total_penalty == sum(w * var for name, w, var in penalty_terms))
            model.Minimize(total_penalty)
            print("Objective function set to minimize soft constraint penalties.")

        # --- Phase 4: Solving ---
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 8
        solver.parameters.max_time_in_seconds = float(time_limit)
        
        print(f"\n--- Starting SAT Solver (Time limit: {time_limit}s) ---")
        status = solver.Solve(model)
        
        # --- Phase 5: Processing Results ---
        final_schedule = []
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            print(f"✅ Solver found a solution with status: {solver.StatusName(status)}")
            if penalty_terms:
                print(f"  - Final objective value (total penalty): {solver.ObjectiveValue()}")
            
            for key, var in variables.items():
                if solver.Value(var) == 1:
                    b_id, session_id, f_id, r_id, t_start = key
                    course_id = session_id.split('_S')[0]
                    final_schedule.append((f_id, course_id, t_start, r_id, b_id))
            return final_schedule, {}, True
        else:
            print(f"❌ Solver could not find a solution. Status: {solver.StatusName(status)}")
            return [], {}, False