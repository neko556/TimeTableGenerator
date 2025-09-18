import pandas as pd
import numpy as np
import random
from faker import Faker

# --- Configuration ---
NUM_STUDENTS = 200
NUM_FACULTY = 35  # Increased resources
NUM_COURSES = 40
NUM_ROOMS = 25   # Increased resources
FACULTY_SLOTS_PER_WEEK = 20  # Increased availability

# New: uniform elective credits for Phase-1 reservation planning
ELECTIVE_CREDITS = 3          # all open electives will use this value
CORE_THEORY_CREDIT_CHOICES = [3, 4]
LAB_CREDITS = 2               # labs count as 2 credits, modeled as 2 contiguous hours

fake = Faker('en_IN')

def run_mock_data_generation():
    """Main orchestrator for generating a complete and solvable dataset."""
    print("--- Generating Solvable Mock Data ---")
    
    # --- Basic Dataframes ---
    students_df = pd.DataFrame([
        {'student_id': f'STU{i:04d}', 'program_id': 'BE-IT', 'current_semester': 1}
        for i in range(1, NUM_STUDENTS + 1)
    ])
    faculty_df = pd.DataFrame([{'faculty_id': f'FAC{i:03d}'} for i in range(1, NUM_FACULTY + 1)])
    rooms_data = [
        {
            'room_id': f'ROOM{i:03d}',
            'room_type': 'Lab' if i % 5 == 0 else 'Classroom',
            'capacity': random.randint(30, 45) if i % 5 == 0 else random.randint(65, 100)
        }
        for i in range(1, NUM_ROOMS + 1)
    ]
    rooms_df = pd.DataFrame(rooms_data)

    # --- Courses with uniform elective credits ---
    courses_data = []
    for i in range(1, NUM_COURSES + 1):
        is_lab = i % 8 == 0
        is_elective = i % 10 == 0

        if is_lab:
            credits = LAB_CREDITS
            duration_hours = 2  # contiguous double-slot lab
        else:
            if is_elective:
                credits = ELECTIVE_CREDITS
            else:
                credits = random.choice(CORE_THEORY_CREDIT_CHOICES)
            duration_hours = credits  # theory: 1 hour per credit (sessions created in preprocessing)

        courses_data.append({
            'course_id': f'CRS{i:03d}',
            'course_type': 'Lab' if is_lab else 'Elective' if is_elective else 'Core',
            'credits': credits,
            'duration_hours': duration_hours,
            'max_size': 30 if is_lab else 100,
            'is_elective': is_elective
        })
    courses_df = pd.DataFrame(courses_data)
    all_course_ids = courses_df['course_id'].tolist()

    # --- Smaller, realistic curriculum basket (cores only for Phase 1) ---
    core_theory_for_basket = [f'CRS{i:03d}' for i in [1, 2, 3, 5, 6, 7]]
    core_labs_for_basket   = [f'CRS{i:03d}' for i in [8, 16]]
    basket_courses_df = pd.DataFrame({
        'basket_id': 'BASKET_MAIN',
        'course_id': core_theory_for_basket + core_labs_for_basket
    })
    course_baskets_df = pd.DataFrame([{'basket_id': 'BASKET_MAIN', 'program_id': 'BE-IT', 'semester': 1}])

    # --- Generate Choices, Expertise, Availability ---
    student_choices_data = []
    electives = courses_df[courses_df['is_elective'] == True]['course_id'].tolist()
    for sid in students_df['student_id']:
        # Each student takes all core courses + 1 elective (electives uniform credits now)
        for cid in (core_theory_for_basket + core_labs_for_basket):
            student_choices_data.append({'student_id': sid, 'chosen_course_id': cid})
        student_choices_data.append({'student_id': sid, 'chosen_course_id': random.choice(electives)})
    student_choices_df = pd.DataFrame(student_choices_data)

    expertise_data = []
    for cid in all_course_ids:
        for fid in random.sample(faculty_df['faculty_id'].tolist(), random.randint(2, 5)):
            expertise_data.append({'faculty_id': fid, 'course_id': cid})
    faculty_expertise_df = pd.DataFrame(expertise_data)

    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    possible_slots = [f"{day}_{h:02d}:00-{(h+1):02d}:00" for day in days for h in range(10, 17) if h != 12]

    faculty_availability_data = []
    for fid in faculty_df['faculty_id']:
        for day in days:
            faculty_availability_data.append({
                'faculty_id': fid,
                'day_of_week': day,
                'time_slot_start': '10:00',
                'time_slot_end': '17:00',
                'availability_type': 'Available'
            })
    faculty_availability_df = pd.DataFrame(faculty_availability_data)

    room_availability_df = []
    for rid in rooms_df['room_id']:
        for day in days:
            room_availability_df.append({
                'room_id': rid,
                'day_of_week': day,
                'time_slot_start': '10:00',
                'time_slot_end': '17:00',
                'availability_status': 'Available'
            })
    room_availability_df = pd.DataFrame(room_availability_df)

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

    print("  - Generated a new, solvable dataset with uniform elective credits.")

if __name__ == '__main__':
    run_mock_data_generation()
