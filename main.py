import pandas as pd
from ga_solver import GeneticAlgorithmTimetable
from sat_solver import TimetableSATModel  # Assuming this is the new OR-Tools version
from time_slots import generate_time_slots
from preprocessor import create_lab_batches, load_data, create_program_batches # Import the new batch function
from validator import validate_student_choices
from tabu_search import TabuSearchTimetable

def main():
    """Main function to run the new batch-based timetabling process."""
    
    print("Starting the timetabling process...")
    data = load_data()
    time_slots, time_slot_map, next_slot_map = generate_time_slots()
    
    # --- 1. PRE-PROCESSING AND BATCH CREATION ---
    # Perform initial data validation
    is_valid = validate_student_choices(data)
    if not is_valid:
        print("\n❌ Validation failed. Please correct the errors in student course choices and try again.")
        return # Exit if data is invalid

    # Create program-level batches and identify core vs. elective courses
    student_batches, batch_core_courses, student_electives, lab_courses = create_program_batches(
        data['students'], data['courses'], data['student_choices']
    )
    data['student_batches'] = student_batches
    data['student_electives'] = student_electives
    data['lab_courses'] = lab_courses # Store labs for the GA later
    data['time_slot_map'] = time_slot_map

   
    # --- 2. SAT SOLVER FOR CORE COURSES (PHASE 1) ---
    print("\nInitializing SAT model for CORE THEORY courses...")
    sat_model = TimetableSATModel(
        data, 
        student_batches, 
        batch_core_courses, 
        time_slot_map,
        next_slot_map
    )
    sat_model.build_model()
    core_schedule_solution = sat_model.solve() # This is the fixed core schedule
    
    if core_schedule_solution:
        print(f"\n✅ SAT Success! Found a valid timetable for {len(core_schedule_solution)} core course assignments.")
        
        # Store the core schedule in the data dict to be used by the GA/Tabu search
        data['core_schedule'] = core_schedule_solution

        # --- 3. GA AND TABU SEARCH FOR ELECTIVES (PHASE 2) ---
        # Note: The GA and Tabu Search now need to be adapted to only optimize electives
        # and respect the fixed core schedule. For this example, we will assume they
        # are run on the full schedule, with the core schedule acting as a hard constraint.

        # Convert the SAT solution (which includes batch_id) to the dictionary format the GA expects
        # The key is now (faculty_id, course_id, time_slot, room_id)
        initial_schedule_dict = {(f, c, t, r): True for f, c, t, r, b in core_schedule_solution}
        
        print("\nStarting Genetic Algorithm to optimize the schedule...")
        ga_solver = GeneticAlgorithmTimetable(
            data, next_slot_map,
            population_size=50,
            generations=100,
            mutation_rate=0.15, # Slightly higher mutation for exploration
            crossover_rate=0.8
        )
        
        # The GA should be initialized with the core schedule as a base
        ga_solver.initialize_population([initial_schedule_dict])
        optimized_schedule_dict = ga_solver.run()
        
        print("\nStarting Tabu Search to polish the schedule...")
        tabu_solver = TabuSearchTimetable(
            data,
            next_slot_map,
            tabu_tenure=10,
            max_iterations=200
        )
        final_polished_schedule = tabu_solver.run(optimized_schedule_dict)

        # --- 4. DISPLAY FINAL RESULTS ---
        final_solution_list = list(final_polished_schedule.keys())
        final_schedule_df = pd.DataFrame(final_solution_list, columns=['Faculty ID', 'Course ID', 'Time Slot', 'Room ID'])
        final_schedule_df[['Day', 'Time']] = final_schedule_df['Time Slot'].str.split('_', expand=True)
        
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        final_schedule_df['Day'] = pd.Categorical(final_schedule_df['Day'], categories=day_order, ordered=True)
        final_schedule_df = final_schedule_df.sort_values(by=['Day', 'Time', 'Room ID']).reset_index(drop=True)

        print("\n--- Generated Timetable ---")
        print(final_schedule_df[['Day', 'Time', 'Course ID', 'Faculty ID', 'Room ID']].to_string())

        # --- Display Individual Faculty Timetables ---
        print("\n" + "="*40)
        print("--- INDIVIDUAL FACULTY TIMETABLES ---")
        print("="*40)
        all_faculty = final_schedule_df['Faculty ID'].unique()
        for faculty_id in all_faculty:
            print(f"\nTimetable for Faculty: {faculty_id}")
            faculty_schedule = final_schedule_df[final_schedule_df['Faculty ID'] == faculty_id]
            print(faculty_schedule[['Day', 'Time', 'Course ID', 'Room ID']].to_string(index=False))

        print("\n" + "="*40)
        print("--- INDIVIDUAL STUDENT TIMETABLE ---")
        print("="*40)

        student_id = input("Enter Student ID to view their timetable: ").strip()

        if student_id not in data['students']['student_id'].values:
            print(f"❌ Student ID {student_id} not found.")
        else:
            # Get all chosen courses for this student
            student_courses = data['student_choices'][data['student_choices']['student_id'] == student_id]['chosen_course_id'].unique().tolist()
            
            # Filter timetable for these courses
            student_schedule = final_schedule_df[final_schedule_df['Course ID'].isin(student_courses)]
            
            if student_schedule.empty:
                print(f"No timetable found for Student {student_id}.")
            else:
                print(f"\n--- Timetable for Student: {student_id} ---")
                print(student_schedule[['Day', 'Time', 'Course ID', 'Faculty ID', 'Room ID']].to_string(index=False))
    else:
            print("\n❌ SAT solver failed. Could not find a valid schedule for core courses.")

if __name__ == "__main__":
    main()