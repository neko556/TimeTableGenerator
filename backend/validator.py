def validate_student_choices(data):
    """
    Validates each student's course choices against their program's basket requirements.
    """
    print("\nValidating student course choices...")
    
    students = data['students']
    student_choices = data['student_choices']
    course_baskets = data['course_baskets']
    courses = data['courses']
    
    all_valid = True

    for _, student in students.iterrows():
        student_id = student['student_id']
        program_id = student.get('program_id') # Assumes Students.csv has 'program_id'
        semester = student.get('current_semester') # Assumes Students.csv has 'current_semester'

        print(f"--- Checking Student: {student_id} (Program: {program_id}, Sem: {semester}) ---")
        
        if not program_id:
            print(f"  - ⚠️ Warning: Cannot determine program for student {student_id}. Skipping.")
            continue

        # Find all baskets required for this student's program and semester
        required_baskets = course_baskets[
            (course_baskets['program_id'] == program_id) &
            (course_baskets['semester'] == semester)
        ]

        if required_baskets.empty:
            print(f"  - ⚠️ Warning: No basket requirements found for this program/semester.")
            continue

        # For each required basket, validate the student's choices
        for _, basket in required_baskets.iterrows():
            basket_id = basket['basket_id']
            required_credits = basket['required_credits']
            
            choices_for_basket = student_choices[
                (student_choices['student_id'] == student_id) &
                (student_choices['basket_id'] == basket_id)
            ]
            
            chosen_course_ids = choices_for_basket['chosen_course_id'].tolist()
            # --- START: ADD DEBUGGING CODE ---
            print(f"    - DEBUG: For basket '{basket_id}', found chosen course IDs: {chosen_course_ids}")
            # Filter the main courses dataframe
            matching_courses = courses[courses['course_id'].isin(chosen_course_ids)]
            print(f"    - DEBUG: Found {len(matching_courses)} matching courses in the main Courses.csv.")
            chosen_credits = courses[courses['course_id'].isin(chosen_course_ids)]['credits'].sum()
            
            if chosen_credits == required_credits:
                print(f"  - ✅ OK: Basket '{basket_id}'. Required: {required_credits}, Chosen: {chosen_credits}")
            else:
                print(f"  - ❌ ERROR: Basket '{basket_id}'. Required: {required_credits}, Chosen: {chosen_credits}")
                all_valid = False

    if all_valid:
        print("\nValidation Complete: All student registrations are valid.")
    else:
        print("\nValidation Complete: Found errors in student registrations.")
        
    return all_valid