import argparse
import pandas as pd

# Import the main pipeline function from main.py
from main import run_timetabling_pipeline
from constraints_io import apply_patch_to_json
# Import the NLP/LLM functions
from nlp_rules import propose_and_apply
from constraints_io import load_constraints

def generate_command(args):
    """Handles the 'generate' command to run the full timetabling pipeline."""
    print("--- Starting Full Timetabling Pipeline ---")
    
    # Run the entire pipeline from main.py
    final_schedule_list, core_batches = run_timetabling_pipeline(time_limit=args.time_limit)
    
    if not final_schedule_list:
        print("\nPipeline finished, but no schedule was generated.")
        return

    # --- Display Final Timetable ---
    print("\n--- ✅ Final Polished Master Timetable ---")
    timetable_df = pd.DataFrame(
        final_schedule_list,
        columns=['Faculty ID', 'Course ID', 'Time Slot', 'Room ID', 'Batch/Group ID']
    )
    timetable_df[['Day', 'Time']] = timetable_df['Time Slot'].str.split('_', n=1, expand=True)
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    timetable_df['Day'] = pd.Categorical(timetable_df['Day'], categories=day_order, ordered=True)
    timetable_df = timetable_df.sort_values(by=['Day', 'Time', 'Room ID']).reset_index(drop=True)
    print(timetable_df.to_string())

    # --- Interactive Student Lookup ---
    while True:
        print("\n" + "=" * 40)
        student_id = input("Enter Student ID to view timetable (or type 'exit' to quit): ")
        if student_id.lower() == 'exit':
            break
        
        core_batch = next((name for name, students in core_batches.items() if student_id in students), None)
        if not core_batch:
            print(f"Student {student_id} not found in any batch.")
            continue
            
        print(f"\n--- Timetable for Student: {student_id} ---")
        student_schedule_df = timetable_df[timetable_df['Batch/Group ID'] == core_batch]
        
        if student_schedule_df.empty:
            print("No classes found for this student in the final schedule.")
        else:
            print(student_schedule_df[['Day', 'Time', 'Course ID', 'Faculty ID', 'Room ID']].to_string(index=False))

# In cli.py
# In cli.py

def propose_command(args):
    """Handles the 'propose' command to add a new constraint via NLP."""
    print(f"--- Proposing new constraint: '{args.nl_text}' ---")
    
    context_snippets = {
        "constraints_json": '{}',
        "sat_solver_py": "# sat_solver.py content...",
        "rule_engine_py": "# rule_engine.py content...",
    }
    
    # This function now returns a patch dictionary or an empty one
    patch = propose_and_apply(
        nl_text=args.nl_text,
        constraints_path=args.constraints_file,
        context_snippets=context_snippets,
        prompts_path="./prompts"
    )
    
    # This if/else block now works as intended
    if patch:
        apply_patch_to_json(args.constraints_file, patch)
        print(f"\n--- ✅ Action Taken: Patch successfully applied. ---")
        print(f"Verify the new rule in '{args.constraints_file}'.")
    else:
        print("\n--- No Action Taken ---")
def main():
    parser = argparse.ArgumentParser(description="TimeGen-4: University Timetabling System")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")
    
    # --- Generate Command ---
    parser_gen = subparsers.add_parser("generate", help="Run the full timetabling pipeline.")
    parser_gen.add_argument("--time-limit", type=int, default=300, help="Time limit for the SAT solver in seconds.")
    parser_gen.set_defaults(func=generate_command)
    
    # --- Propose Command ---
    parser_prop = subparsers.add_parser("propose", help="Propose a new constraint using natural language.")
    parser_prop.add_argument("--nl-text", type=str, required=True, help="The natural language text for the new constraint.")
    parser_prop.add_argument("--constraints-file", type=str, default="constraints.json", help="Path to the constraints JSON file.")
    parser_prop.set_defaults(func=propose_command)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()