import argparse
import json
from dotenv import load_dotenv
from nlp_rules import generate_new_rule_with_llm

# Local imports from your project
from preprocessor import assemble_data
from nlp_rules import propose_and_apply, dry_run_constraints, deep_merge_constraints

def load_rules_from_json(filepath: str = "constraints.json") -> dict:
    """
    Loads the existing set of rules from the constraints.json file.
    """
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[WARN] Constraints file not found at '{filepath}'. Starting with empty rules.")
        return {}

def process_and_validate_prompt(prompt: str):
    """
    Orchestrates the full NLP-to-Rule-Engine pipeline.
    """
    # --- [1/4] Load Data and Rules ---
    print("[1/4] Loading data and existing rules...")
    
    # Load existing rules from file
    all_rules = load_rules_from_json("constraints.json")
    
    # Load all timetable data from your preprocessor
    (
        time_slot_map,
        next_slot_map,
        core_batches,
        core_batch_sessions,
        elective_groups,
        elective_group_sessions,
        data_full,
    ) = assemble_data()
    print("      Data and rules loaded successfully.")

    # --- [2/4] Analyze Prompt ---
    print(f"[2/4] Analyzing prompt: '{prompt}'")

    # Call the parser pipeline, passing the full data and time slot map
    result = propose_and_apply(
        nl_text=prompt,
        data=data_full,
        time_slot_map=time_slot_map,
    )

    patch = result.get("patch", {})
    source = result.get("source", "none")
    label = "NLP" if source == "nlp" else ("Gemini" if source == "gemini" else "No Parser")
    patch = result.get("patch", {})

    if not patch:
        print("[INFO] No existing rule could be applied. Attempting to generate a new rule...")
        try:
            with open("rule_engine.py", "r") as f:
                rule_engine_code = f.read()
            generate_new_rule_with_llm(prompt, rule_engine_code)
        except FileNotFoundError:
            print("[ERROR] Could not find rule_engine.py to generate a new rule.")
        
        # Set validation_results for a clean exit
        validation_results = {"status": "No rule applied. A new rule may have been suggested."}
    else:
        # This is the existing logic for when a patch IS found
        print("[3/4] Applying new facts and running validation (dry-run)...")
        merged_rules = deep_merge_constraints(all_rules, patch)
        validation_results = dry_run_constraints(...) # Your existing call
        if validation_results.get("is_feasible", False):
            save_rules_to_json(merged_rules)



    # --- [4/4] Validation Results ---
    print("--- [4/4] Validation Results ---")
    print(json.dumps(validation_results, indent=2))
    print("--------------------------------")


def save_rules_to_json(rules: dict, filepath: str = "constraints.json"):
    """Saves the provided rules dictionary to the constraints.json file."""
    print(f"[INFO] Saving updated rules to '{filepath}'...")
    try:
        with open(filepath, 'w') as f:
            json.dump(rules, f, indent=2)
        print("[INFO] Rules saved successfully.")
    except Exception as e:
        print(f"[ERROR] Failed to save rules: {e}")


# --- Entry Point ---
if __name__ == "__main__":
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Process a natural language prompt and validate it against the rule engine."
    )
    parser.add_argument(
        "prompt", 
        type=str, 
        help="The natural language prompt to process. Enclose in quotes."
    )
    args = parser.parse_args()
    
    process_and_validate_prompt(args.prompt)
