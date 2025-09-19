import pandas as pd
from collections import defaultdict

class RuleEngine:
    """
    Compiles declarative hard and soft constraints from a JSON config into
    CP-SAT model constraints by recognizing and dispatching rule patterns.
    """
    def __init__(self, time_slot_map, next_slot_map):
        self.time_slot_map = time_slot_map
        self.next_slot_map = next_slot_map

    # ------------- Private Utilities -------------
    @staticmethod
    def _enabled(entry):
        return bool(entry and entry.get("enabled", False))

    @staticmethod
    def _w100(v, default=1.0):
        try:
            return int(round(float(v) * 100))
        except Exception:
            return int(round(float(default) * 100))

    def _iter_assignments(self, variables):
        """Normalizes solver variables into a stream of consistent fact dictionaries."""
        for key, var in variables.items():
            b_id, session_id, f_id, r_id, t_start = key
            yield {
                "batch_id": b_id,
                "session_id": session_id,
                "course_id": session_id.split('_S')[0],
                "faculty_id": f_id,
                "room_id": r_id,
                "t_start": t_start,
                "day_of_week": t_start.split('_')[0],
                "var": var,
            }

    # ------------- Hard Constraint Compilation -------------
    def compile_hard(self, model, variables, hard_cfg):
        """
        Generically compiles hard constraints by dispatching to pattern handlers.
        """
        for rule_id, rule_data in hard_cfg.items():
            if not self._enabled(rule_data):
                continue

            pattern = rule_data.get("pattern")
            
            # --- The Dispatcher for Hard Rules ---
            if pattern == "forbid_by_attribute":
                self._apply_forbid_by_attribute_pattern(model, variables, rule_data)
            # elif pattern == "another_hard_pattern":
            #     self._apply_another_hard_pattern(...) # Future extension
            else:
                print(f"[warn] Unknown hard constraint pattern: '{pattern}' for rule '{rule_id}'")
        print("[Rule Engine] Hard constraints compiled.")

    def _apply_forbid_by_attribute_pattern(self, model, variables, rule):
        """
        Handler for rules that forbid an assignment if all filter conditions match.
        """
        filters = rule.get("filter", {})
        if not filters:
            return

        for assignment_fact in self._iter_assignments(variables):
            is_match = True
            for key, required_values in filters.items():
                if assignment_fact.get(key) not in required_values:
                    is_match = False
                    break
            
            if is_match:
                model.Add(assignment_fact["var"] == 0)
    
    # ------------- Soft Constraint Compilation -------------
    def compile_soft(self, model, variables, soft_cfg):
        """
        Generically compiles soft constraints and returns penalty terms.
        """
        terms = []
        for rule_id, rule_data in soft_cfg.items():
            if not self._enabled(rule_data):
                continue

            pattern = rule_data.get("pattern")

            # --- The Dispatcher for Soft Rules ---
            if pattern == "apply_penalty_by_attribute":
                new_terms = self._apply_penalty_by_attribute_pattern(model, variables, rule_id, rule_data)
                terms.extend(new_terms)
            # elif pattern == "another_soft_pattern":
            #     new_terms = self._apply_other_soft_pattern(...) # Future extension
            #     terms.extend(new_terms)
            else:
                print(f"[warn] Unknown soft constraint pattern: '{pattern}' for rule '{rule_id}'")
        
        print("[Rule Engine] Soft constraints compiled.")
        return terms

    def _apply_penalty_by_attribute_pattern(self, model, variables, rule_id, rule):
        """
        Handler for rules that apply a penalty if an assignment matches all filter conditions.
        """
        filters = rule.get("filter", {})
        if not filters:
            return []
        
        w = self._w100(rule.get("weight", 1.0))
        penalty_terms = []

        for assignment_fact in self._iter_assignments(variables):
            is_match = True
            for key, required_values in filters.items():
                if assignment_fact.get(key) not in required_values:
                    is_match = False
                    break
            
            if is_match:
                penalty_var = model.NewBoolVar(f"p_{rule_id}_{assignment_fact['session_id']}_{assignment_fact['t_start']}")
                model.Add(assignment_fact["var"] == 1).OnlyEnforceIf(penalty_var)
                model.Add(assignment_fact["var"] == 0).OnlyEnforceIf(penalty_var.Not())
                penalty_terms.append((rule_id, w, penalty_var))

        return penalty_terms
    def calculate_penalty_score(self, individual, soft_cfg, sid_to_course):
            """
            Calculates a total penalty score for a given GA/Tabu individual (a concrete schedule)
            based on the soft constraint configuration.
            """
            total_penalty = 0.0
            if not individual:
                return 0.0

            for rule_id, rule_data in soft_cfg.items():
                if not self._enabled(rule_data):
                    continue
                
                pattern = rule_data.get("pattern")
                
                # --- Dispatcher for Scoring ---
                if pattern == "apply_penalty_by_attribute":
                    filters = rule_data.get("filter", {})
                    weight = float(rule_data.get("weight", 1.0))
                    if not filters:
                        continue

                    # Iterate over each scheduled session in the GA individual
                    for (f_id, sid, t_start, r_id) in individual.keys():
                        
                        # Create a "fact" dictionary for the current assignment
                        assignment_fact = {
                            "session_id": sid,
                            "course_id": sid_to_course.get(sid),
                            "faculty_id": f_id,
                            "room_id": r_id,
                            "t_start": t_start,
                            "day_of_week": t_start.split('_')[0],
                        }
                        
                        # Check if the assignment matches the rule's filter
                        is_match = True
                        for key, required_values in filters.items():
                            if assignment_fact.get(key) not in required_values:
                                is_match = False
                                break
                        
                        if is_match:
                            total_penalty += weight
                
                # Add 'elif' blocks here to handle other patterns in the future

            return total_penalty