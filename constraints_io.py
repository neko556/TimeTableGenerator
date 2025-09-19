import json

def load_constraints(filepath: str) -> dict:
    """Loads the constraints.json file."""
    try:
        with open(filepath, 'r') as f:
            constraints = json.load(f)
    except FileNotFoundError:
        constraints = {}
    
    if "hard_constraints" not in constraints:
        constraints["hard_constraints"] = {}
    if "soft_constraints" not in constraints:
        constraints["soft_constraints"] = {}
        
    return constraints

def save_constraints(filepath: str, data: dict):
    """Saves the constraints dictionary back to a JSON file."""
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)
    print(f"[io] Successfully saved updated constraints to {filepath}")

def apply_patch_to_json(filepath: str, patch: dict):
    """Loads a JSON file, applies a patch, and saves it back."""
    constraints = load_constraints(filepath)
    
    for category, ops in patch.items():
        if category in constraints:
            for op, rules in ops.items():
                if op == "add":
                    for rule_id, rule_body in rules.items():
                        constraints[category][rule_id] = rule_body
                        print(f"  - Added rule '{rule_id}' to '{category}'")
    
    save_constraints(filepath, constraints)
# constraints_io.py

import json
import copy
from typing import Dict, Any

def deep_merge_constraints(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively merges a patch dictionary into a base dictionary.
    This function is "pure"—it returns a new dictionary and does not modify the original.
    """
    res = copy.deepcopy(base or {})
    for k, v in (patch or {}).items():
        if k in res and isinstance(res[k], dict) and isinstance(v, dict):
            res[k] = deep_merge_constraints(res[k], v)
        else:
            res[k] = copy.deepcopy(v)
    return res

def apply_patch_to_json(file_path: str, patch: Dict[str, Any]):
    """
    Loads a JSON file, safely merges a patch into it, and saves it back.
    """
    if not patch:
        print("[io] WARN: Received an empty patch. No changes will be applied.")
        return

    try:
        # Step 1: Read existing data. Handle cases where the file is missing or empty.
        existing_data = {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"[io] WARN: '{file_path}' not found or is invalid. A new file will be created.")

        # Step 2: Merge the patch. This is the most critical part.
        # You MUST assign the returned value of the merge function to a variable.
        merged_data = deep_merge_constraints(existing_data, patch)

        # Step 3: Write the newly merged data back to the file.
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(merged_data, f, indent=4)
        
        print(f"[io] Successfully saved updated constraints to {file_path}")

    except Exception as e:
        print(f"[io] ERROR: Failed to apply patch to '{file_path}'. Reason: {e}")