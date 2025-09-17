import pandas as pd
import numpy as np
import math


def load_data():
    """
    Load all required data CSV files into pandas DataFrames and return as a dictionary.
    File paths should be updated to where your CSVs are stored.
    """

    students = pd.read_csv('Students.csv')
    faculty = pd.read_csv('Faculty.csv')
    courses = pd.read_csv('Courses.csv')
    rooms = pd.read_csv('Rooms.csv')

    #student_registrations = pd.read_csv('Student_Registrations.csv')
    student_choices = pd.read_csv('Student_Choices.csv')
    course_baskets = pd.read_csv('Course_Baskets.csv')
    basket_courses = pd.read_csv('Basket_Courses.csv')
    faculty_expertise = pd.read_csv('Faculty_Expertise.csv')
    faculty_availability = pd.read_csv('Faculty_Availability.csv')
    room_availability = pd.read_csv('Room_Availability.csv')
    scheduling_constraints = pd.read_csv('Scheduling_Constraints.csv')

    students['student_id'] = students['student_id'].astype(str).str.strip()
    faculty['faculty_id'] = faculty['faculty_id'].astype(str).str.strip()
    courses['course_id'] = courses['course_id'].astype(str).str.strip()
    
    student_choices['student_id'] = student_choices['student_id'].astype(str).str.strip()
    student_choices['chosen_course_id'] = student_choices['chosen_course_id'].astype(str).str.strip()
    
    # Get the unique course IDs from the main course list
    main_course_ids = sorted(courses['course_id'].unique().tolist())
    print(f"Unique Course IDs from Courses.csv: {main_course_ids}")
    
    # Get the unique course IDs from the student choices list
    choice_course_ids = sorted(student_choices['chosen_course_id'].unique().tolist())
    print(f"Unique Course IDs from Student_Choices.csv: {choice_course_ids}")
    
    # Find which IDs are in choices but not in the main course list
    missing_ids = set(choice_course_ids) - set(main_course_ids)
    if missing_ids:
        print(f"MISMATCH DETECTED! These IDs are in choices but NOT in Courses.csv: {list(missing_ids)}")
    else:
        print("Data looks consistent. All chosen course IDs exist in the main course list.")
        
    print("--- END DEBUGGING ---")
    # --- END: NEW DEBUGGING CODE ---

    data = {
        'students': students,
        'faculty': faculty,
        'courses': courses,
        'rooms': rooms,
        
        'faculty_expertise': faculty_expertise,
        'faculty_availability': faculty_availability,
        'room_availability': room_availability,
        'scheduling_constraints': scheduling_constraints,
        'student_choices': student_choices,
        'course_baskets': course_baskets,
        'basket_courses': basket_courses,
    }

    return data
def create_lab_batches(courses_df, choices_df, expertise_df):
    """
    Splits courses into smaller lab batches and updates related data.
    """
    print("Running pre-processor to create lab batches and update expertise...")
    
    # Make copies to avoid modifying the original dataframes
    new_courses_df = courses_df.copy()
    new_registrations_df = choices_df.copy() # <-- FIX 1: Initialize this dataframe
    new_expertise_df = expertise_df.copy()

    batch_student_map = {}
    courses_to_split = courses_df[courses_df['max_size'].notna() & (courses_df['max_size'] > 0)]

    for index, course in courses_to_split.iterrows():
        course_id = course['course_id']
        max_size = course['max_size']

        enrolled_students = choices_df[choices_df['chosen_course_id'] == course_id]
        num_students = len(enrolled_students)

        if num_students == 0:
            continue

        

        num_batches = math.ceil(num_students / max_size)
        student_list = enrolled_students['student_id'].tolist()


        if num_batches > 1:
            print(f"Splitting '{course_id}' for {num_students} students into {num_batches} batches.")
            
            original_experts = expertise_df[expertise_df['course_id'] == course_id]

            # 1. Remove original course, registrations, and expertise
            new_courses_df = new_courses_df[new_courses_df['course_id'] != course_id]
            # --- FIX 2: Use the correct column name 'chosen_course_id' ---
            new_registrations_df = new_registrations_df[new_registrations_df['chosen_course_id'] != course_id]
            # -----------------------------------------------------------
            new_expertise_df = new_expertise_df[new_expertise_df['course_id'] != course_id]

            # 2. Create new batches and distribute students
            student_list = enrolled_students['student_id'].tolist()
            student_chunks = np.array_split(student_list, num_batches)


            for i, batch_students in enumerate(student_chunks):
                batch_letter = chr(ord('A') + i)
                new_course_id = f"{course_id}-{batch_letter}"
                
                # Add new course batch
                new_course_row = course.copy()
                new_course_row['course_id'] = new_course_id
                new_courses_df = pd.concat([new_courses_df, new_course_row.to_frame().T], ignore_index=True)
                batch_student_map[new_course_id] = batch_students
                
                # Add new student registrations for the batch
                for student_id in batch_students:
                    new_reg_row = {
                        'student_id': student_id,
                        'chosen_course_id': new_course_id,
                        'basket_id': 'FROM_LAB_SPLIT'
                    }
                    new_registrations_df = pd.concat([new_registrations_df, pd.DataFrame([new_reg_row])], ignore_index=True)

                # Add new expertise entries for the batch
                for _, expert_row in original_experts.iterrows():
                    new_expert_row = expert_row.copy()
                    new_expert_row['course_id'] = new_course_id
                    new_expertise_df = pd.concat([new_expertise_df, new_expert_row.to_frame().T], ignore_index=True)
        else:
            batch_student_map[course_id] = student_list

    return new_courses_df, new_registrations_df, new_expertise_df,batch_student_map
def create_program_batches(students_df, courses_df, choices_df, batch_size=50): # Adjusted batch size
    """
    Splits students into batches and separates core theory, labs, and electives.
    """
    print("Creating program-level batches and separating course types...")

    # --- FIX: Separate courses into three distinct categories ---
    core_theory_courses = courses_df[
        (courses_df['is_elective'] == False) &
        (courses_df['course_type'].str.lower() != 'lab')
    ]['course_id'].tolist()

    lab_courses = courses_df[courses_df['course_type'].str.lower() == 'lab']['course_id'].tolist()
    
    elective_courses = courses_df[courses_df['is_elective'] == True]['course_id'].tolist()

    student_batches = {}
    batch_core_courses = {} # This will now ONLY contain theory courses
    student_elective_choices = {}

    program_id = students_df['program_id'].iloc[0]
    all_students = students_df['student_id'].tolist()
    num_batches = math.ceil(len(all_students) / batch_size)

    for i in range(num_batches):
        batch_name = f"{program_id}-Batch-{chr(ord('A') + i)}"
        start_index = i * batch_size
        end_index = start_index + batch_size
        batch_students = all_students[start_index:end_index]
        student_batches[batch_name] = batch_students

        # Assign ONLY core theory courses to the batch for the SAT solver
        batch_core_courses[batch_name] = core_theory_courses

        for student_id in batch_students:
            student_choices = choices_df[choices_df['student_id'] == student_id]
            electives = student_choices[student_choices['chosen_course_id'].isin(elective_courses)]
            student_elective_choices[student_id] = electives['chosen_course_id'].tolist()

    print(f"Created {len(student_batches)} batches for program {program_id}.")
    # Return the lab courses separately
    return student_batches, batch_core_courses, student_elective_choices, lab_courses