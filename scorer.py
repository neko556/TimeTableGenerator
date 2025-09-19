def _iter_assignment_facts(assignments):
    """Helper to convert raw assignment tuples into structured fact dictionaries."""
    it = assignments.keys() if isinstance(assignments, dict) else assignments
    for (f_id, sid, t_start, r_id) in it:
        # This structure must match the attributes used in your constraints.json filters
        yield {
            "faculty_id": f_id,
            "session_id": sid,
            "t_start": t_start,
            "room_id": r_id,
            "course_id": sid.split("::")[2],
            "day_of_week": t_start.split("_")[0]
        }


def soft_penalty(assignments, soft_cfg, next_slot_map=None):
    """
    Calculates the total penalty for a schedule by dynamically applying
    soft constraint rules from a configuration dictionary.
    """
    total_penalty = 0.0

    # Generic loop to process all soft constraints from constraints.json
    for rule_id, rule_data in soft_cfg.items():
        if not rule_data.get("enabled", False):
            continue

        pattern = rule_data.get("pattern")
        
        # Dispatch to the correct pattern handler
        if pattern == "apply_penalty_by_attribute":
            filters = rule_data.get("filter", {})
            weight = float(rule_data.get("weight", 1.0))
            
            if not filters:
                continue

            # Iterate through each scheduled class
            for assignment_fact in _iter_assignment_facts(assignments):
                is_match = True
                # Check if the class matches all filter conditions
                for key, required_values in filters.items():
                    if assignment_fact.get(key) not in required_values:
                        is_match = False
                        break
                
                # If it's a match, add the penalty
                if is_match:
                    total_penalty += weight
    
    return total_penalty