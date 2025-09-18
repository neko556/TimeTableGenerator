import pandas as pd
import numpy as np
import random
from faker import Faker

# --- Configuration ---
NUM_STUDENTS = 200
NUM_FACULTY = 35
NUM_COURSES = 40
NUM_ROOMS = 25
FACULTY_SLOTS_PER_WEEK = 20

# Credits policy
ELECTIVE_CREDITS = 3           # all electives use this value
CORE_THEORY_CREDIT_CHOICES = [3, 4]
LAB_CREDITS = 2                # labs = 2 contiguous hours

fake = Faker('en_IN')

def run_mock_data_generation():
    print("--- Generating Solvable Mock Data (CORE + ELECTIVE baskets) ---")

    # --- Basic Dataframes ---
    students_df = pd.DataFrame([
        {'student_id': f'STU{i:04d}', 'program_id': 'BE-IT', 'current_semester': 1}
        for i in range(1, NUM_STUDENTS + 1)
    ])
    faculty_df = pd.DataFrame([{'faculty_id': f'FAC{i:03d}'} for i in range(1, NUM_FACULTY + 1)])

    rooms_data = []
    for i in range(1, NUM_ROOMS + 1):
        is_lab_room = (i % 5 == 0)
        rooms_data.append({
            'room_id': f'ROOM{i:03d}',
            'room_type': 'Lab' if is_lab_room else 'Classroom',
            'capacity': random.randint(30, 45) if is_lab_room else random.randint(65, 100)
        })
    rooms_df = pd.DataFrame(rooms_data)

    # --- Courses with uniform elective credits ---
    courses_data = []
    for i in range(1, NUM_COURSES + 1):
        is_lab = (i % 8 == 0)
        is_elective = (i % 10 == 0)  # roughly 4 electives among 40

        if is_lab:
            credits = LAB_CREDITS
            duration_hours = 2
        else:
            credits = ELECTIVE_CREDITS if is_elective else random.choice(CORE_THEORY_CREDIT_CHOICES)
            duration_hours = credits

        courses_data.append({
            'course_id': f'CRS{i:03d}',
            'course_type': 'Lab' if is_lab else ('Elective' if is_elective else 'Core'),
            'credits': credits,
            'duration_hours': duration_hours,
            'max_size': 30 if is_lab else 100,
            'is_elective': is_elective
        })
    courses_df = pd.DataFrame(courses_data)

    # Identify specific ids we'll use for baskets (stable sample based on the above pattern)
    core_theory_for_basket = [f'CRS{i:03d}' for i in [1, 2, 3, 5, 6, 7]]
    core_labs_for_basket   = [f'CRS{i:03d}' for i in [8, 16]]
    core_main_list = core_theory_for_basket + core_labs_for_basket

    # Electives list (only true electives)
    elective_ids = courses_df[courses_df['is_elective'] == True]['course_id'].tolist()
    # Pick 3–4 electives for Sem-1 offering
    sem1_electives = elective_ids[:4] if len(elective_ids) >= 4 else elective_ids

    # --- Basket_Courses: CORE + ELECTIVE baskets ---
    basket_courses_rows = []
    # CORE basket (mandatory curriculum)
    for cid in core_main_list:
        basket_courses_rows.append({'basket_id': 'BASKET_MAIN', 'course_id': cid})
    # ELECTIVE basket for Sem-1
    for cid in sem1_electives:
        basket_courses_rows.append({'basket_id': 'BASKET_MAIN_ELECTIVE', 'course_id': cid})
    basket_courses_df = pd.DataFrame(basket_courses_rows)

    # --- Course_Baskets: add basket_type and elective_credits ---
    # Compute core basket credits sum for consistency (not used for choices)
    core_credits = int(courses_df[courses_df['course_id'].isin(core_main_list)]['credits'].sum())

    course_baskets_df = pd.DataFrame([
        {'basket_id': 'BASKET_MAIN', 'program_id': 'BE-IT', 'semester': 1, 'basket_type': 'CORE', 'elective_credits': core_credits},
        {'basket_id': 'BASKET_MAIN_ELECTIVE', 'program_id': 'BE-IT', 'semester': 1, 'basket_type': 'ELECTIVE', 'elective_credits': ELECTIVE_CREDITS},
        # Example future semester rows (left present for structure; can be adjusted/removed)
        {'basket_id': 'BASKET_M1', 'program_id': 'BE-IT', 'semester': 3, 'basket_type': 'CORE', 'elective_credits': 0},
        {'basket_id': 'BASKET_M1_ELECTIVE', 'program_id': 'BE-IT', 'semester': 3, 'basket_type': 'ELECTIVE', 'elective_credits': ELECTIVE_CREDITS},
    ])

    # --- Student choices: only electives (no choices for CORE baskets) ---
    student_choices_rows = []
    for sid in students_df['student_id']:
        # Each student chooses exactly one elective from the Sem-1 elective basket
        if sem1_electives:
            student_choices_rows.append({'student_id': sid, 'basket_id': 'BASKET_MAIN_ELECTIVE', 'chosen_course_id': random.choice(sem1_electives)})
    student_choices_df = pd.DataFrame(student_choices_rows)

    # --- Faculty expertise: multiple experts per course ---
    expertise_rows = []
    faculty_ids = faculty_df['faculty_id'].tolist()
    for cid in courses_df['course_id']:
        k = random.randint(2, 5)
        for fid in random.sample(faculty_ids, k):
            expertise_rows.append({'faculty_id': fid, 'course_id': cid})
    faculty_expertise_df = pd.DataFrame(expertise_rows)

    # --- Availability windows (coarse, wide availability) ---
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

    faculty_availability_rows = []
    for fid in faculty_df['faculty_id']:
        for day in days:
            faculty_availability_rows.append({
                'faculty_id': fid,
                'day_of_week': day,
                'time_slot_start': '10:00',
                'time_slot_end': '17:00',
                'availability_type': 'Available'
            })
    faculty_availability_df = pd.DataFrame(faculty_availability_rows)

    room_availability_rows = []
    for rid in rooms_df['room_id']:
        for day in days:
            room_availability_rows.append({
                'room_id': rid,
                'day_of_week': day,
                'time_slot_start': '10:00',
                'time_slot_end': '17:00',
                'availability_status': 'Available'
            })
    room_availability_df = pd.DataFrame(room_availability_rows)

    # --- Save all to CSV ---
    students_df.to_csv('Students.csv', index=False)
    faculty_df.to_csv('Faculty.csv', index=False)
    rooms_df.to_csv('Rooms.csv', index=False)
    courses_df.to_csv('Courses.csv', index=False)
    student_choices_df.to_csv('Student_Choices.csv', index=False)
    faculty_expertise_df.to_csv('Faculty_Expertise.csv', index=False)
    faculty_availability_df.to_csv('Faculty_Availability.csv', index=False)
    room_availability_df.to_csv('Room_Availability.csv', index=False)
    course_baskets_df.to_csv('Course_Baskets.csv', index=False)
    basket_courses_df.to_csv('Basket_Courses.csv', index=False)

    print("  - Generated dataset with CORE and ELECTIVE baskets (student choices only for electives).")

if __name__ == '__main__':
    run_mock_data_generation()
