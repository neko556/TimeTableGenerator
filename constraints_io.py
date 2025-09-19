import argparse
import json
import pandas as pd
from dotenv import load_dotenv
from preprocessor import assemble_data
from nlp_rules import propose_and_apply

# --- Main CLI Application ---

def main():
    """
    Command-line interface to test the hybrid NLP rule parsing system.
    """
    
    load_dotenv()
    
    parser = argparse.ArgumentParser(
        description="Parse a natural language rule into a JSON constraint patch."
    )
    parser.add_argument("text", type=str, help="The natural language rule to parse.")
    parser.add_argument(
        "--apply", 
        action="store_true", 
        help="If set, the script will simulate applying the change (requires full dry-run logic)."
    )
    args = parser.parse_args()

    print("--- Starting NLP Rule Parser ---")

    try:
        # 1. Load all necessary data artifacts using your preprocessor
        print("[1/3] Loading and preprocessing data...")
        (
            time_slot_map,
            next_slot_map,
            core_batches,
            core_batch_sessions,
            elective_groups,
            elective_group_sessions,
            data_full,
        ) = assemble_data()
        print("      Data loaded successfully.")

        # 2. Call the main NLP orchestrator function
        print(f"[2/3] Parsing request: '{args.text}'")
        result = propose_and_apply(
            nl_text=args.text,
            data=data_full,
            time_slot_map=time_slot_map,
            next_slot_map=next_slot_map,
            core_batches=core_batches,
            core_batch_sessions=core_batch_sessions
            # Add any other arguments your full propose_and_apply function might need
        )
        print("      Parsing complete.")

        # 3. Display the final result
        print("[3/3] Result from NLP pipeline:")
        # The 'patch' is the main JSON output
        # The 'status' indicates if it's ready for the next step (validation/dry-run)
        print(json.dumps(result, indent=2))

        if args.apply:
            print("\n--- Simulation: Applying Patch ---")
            # In a real application, you would now take the `result['patch']`
            # and run it through your validation and dry-run solvers.
            print("NOTE: This is where you would merge the patch and run a solver simulation.")
            
    except Exception as e:
        print(f"\n--- An Error Occurred ---")
        print(f"Error: {e}")
        print("---------------------------")

if __name__ == "__main__":
    main()
