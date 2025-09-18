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
def _write_constraints_csvs(days=None):
    if days is None:
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    # Hard constraints: feasibility + elective channeling
    hard_rows = [
        {
            'constraint_id': 'teacher_no_overlap', 'enabled': 'TRUE', 'scope_level': 'global',
            'program_id': '', 'semesters': '', 'faculty_ids': '', 'course_ids': '',
            'params': '', 'notes': ''
        },
        {
            'constraint_id': 'room_no_overlap', 'enabled': 'TRUE', 'scope_level': 'global',
            'program_id': '', 'semesters': '', 'faculty_ids': '', 'course_ids': '',
            'params': '', 'notes': ''
        },
        {
            'constraint_id': 'availability_forbid', 'enabled': 'TRUE', 'scope_level': 'global',
            'program_id': '', 'semesters': '', 'faculty_ids': '', 'course_ids': '',
            'params': '', 'notes': ''
        },
        {
            'constraint_id': 'lab_contiguity', 'enabled': 'TRUE', 'scope_level': 'global',
            'program_id': '', 'semesters': '', 'faculty_ids': '', 'course_ids': '',
            'params': '', 'notes': ''
        },
        {
            'constraint_id': 'core_vs_elec_windows', 'enabled': 'TRUE', 'scope_level': 'program',
            'program_id': 'BE-IT', 'semesters': '1', 'faculty_ids': '', 'course_ids': '',
            'params': 'enforce=TRUE', 'notes': 'reserve elective windows'
        },
    ]
    hard_cols = ['constraint_id','enabled','scope_level','program_id','semesters','faculty_ids','course_ids','params','notes']
    pd.DataFrame(hard_rows, columns=hard_cols).to_csv('HardConstraints.csv', index=False)

    # Build time keys matching "Day_HH:MM-HH:MM"
    # Assume hour range 10..17 excluding 12 as in your generator
    slot_keys = [f"{d}_{h:02d}:00-{(h+1):02d}:00" for d in days for h in range(10, 17) if h != 12]
    # Choose early and late sets that are guaranteed present
    early = [f"{d}_10:00-11:00" for d in days]
    # Late: pick the last modeled hour (16:00-17:00) and also common z_t from Phase-1 (15:00-16:00)
    last = [f"{d}_16:00-17:00" for d in days] + [f"{d}_15:00-16:00" for d in days]

    soft_rows = [
        {
            'constraint_id': 'avoid_early_slot', 'enabled': 'TRUE', 'weight': 2.0,
            'scope_level': 'program', 'program_id': 'BE-IT', 'semesters': '1',
            'faculty_ids': '', 'course_ids': '',
            'params': 'early_slots=' + "|".join(early),
            'priority': 2
        },
        {
            'constraint_id': 'avoid_last_slot', 'enabled': 'TRUE', 'weight': 3.0,
            'scope_level': 'program', 'program_id': 'BE-IT', 'semesters': '1',
            'faculty_ids': '', 'course_ids': '',
            'params': 'last_slot_by_day=' + "|".join(last),
            'priority': 2
        },
        {
            'constraint_id': 'faculty_pref_hours', 'enabled': 'TRUE', 'weight': 2.0,
            'scope_level': 'faculty', 'program_id': '', 'semesters': '',
            'faculty_ids': 'FAC001|FAC002', 'course_ids': '',
            'params': 'dispreferred=Friday_16:00-17:00',
            'priority': 2
        },
    ]
    soft_cols = ['constraint_id','enabled','weight','scope_level','program_id','semesters','faculty_ids','course_ids','params','priority']
    pd.DataFrame(soft_rows, columns=soft_cols).to_csv('SoftConstraints.csv', index=False)


if __name__ == '__main__':
    run_mock_data_generation()
    _write_constraints_csvs()
        
    print("  - Generated a new, solvable dataset with uniform elective credits and CSV constraints.")
