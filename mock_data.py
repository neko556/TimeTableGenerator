import pandas as pd
import numpy as np
import random
import json
from faker import Faker

# --- Configuration for a smaller, solvable dataset ---
NUM_STUDENTS = 80
NUM_FACULTY = 20
NUM_COURSES = 15
NUM_ROOMS = 10
ELECTIVE_CREDITS = 3
LAB_CREDITS = 2

def generate_data_csvs():
    """Generates a complete and solvable dataset and saves to CSV files."""
    print("--- Generating New Mock Data CSVs ---")
    
    # --- Basic Dataframes ---
    students_df = pd.DataFrame([
        {'student_id': f'STU{i:04d}', 'program_id': 'BE-IT', 'current_semester': 1}
        for i in range(1, NUM_STUDENTS + 1)
    ])
    faculty_df = pd.DataFrame([{'faculty_id': f'FAC{i:03d}'} for i in range(1, NUM_FACULTY + 1)])
    
    rooms_data = [
        {
            'room_id': f'LAB{i:02d}', 'room_type': 'Lab', 'capacity': 30
        } for i in range(1, 4) # 3 Labs
    ] + [
        {
            'room_id': f'ROOM{i:03d}', 'room_type': 'Classroom', 'capacity': 70
        } for i in range(1, NUM_ROOMS - 2) # 7 Classrooms
    ]
    rooms_df = pd.DataFrame(rooms_data)

    # --- Courses ---
    courses_data = []
    core_courses = ['CRS001', 'CRS002', 'CRS003']
    lab_courses = ['CRS008']
    elective_courses = ['CRS010']
    
    all_mock_courses = core_courses + lab_courses + elective_courses
    
    for i, cid in enumerate(all_mock_courses):
        is_lab = cid in lab_courses
        is_elective = cid in elective_courses
        credits = LAB_CREDITS if is_lab else ELECTIVE_CREDITS if is_elective else 3
        duration = 2 if is_lab else 1 # Labs are 2 hours, others are 1 hour
        
        courses_data.append({
            'course_id': cid,
            'course_type': 'Lab' if is_lab else 'Elective' if is_elective else 'Core',
            'credits': credits, 'duration_hours': duration, 'max_size': 30 if is_lab else 100,
            'is_elective': is_elective
        })
    courses_df = pd.DataFrame(courses_data)

    # --- Curriculum and Student Choices ---
    curriculum_df = pd.DataFrame([
        {'batch_id': 'BE-IT_Sem1', 'course_id': 'CRS001', 'num_sessions_per_week': 2},
        {'batch_id': 'BE-IT_Sem1', 'course_id': 'CRS002', 'num_sessions_per_week': 2},
        {'batch_id': 'BE-IT_Sem1', 'course_id': 'CRS003', 'num_sessions_per_week': 1},
        {'batch_id': 'BE-IT_Sem1', 'course_id': 'CRS008', 'num_sessions_per_week': 1},
    ])

    student_choices_data = []
    for sid in students_df['student_id']:
        student_choices_data.append({'student_id': sid, 'chosen_course_id': 'CRS010'})
    student_choices_df = pd.DataFrame(student_choices_data)

    # --- Expertise and Availability ---
    expertise_data = []
    for cid in all_mock_courses:
        # Ensure each course has at least 2-3 faculty members who can teach it
        for fid in random.sample(faculty_df['faculty_id'].tolist(), random.randint(2, 3)):
            expertise_data.append({'faculty_id': fid, 'course_id': cid})
    faculty_expertise_df = pd.DataFrame(expertise_data)

    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    faculty_availability_data = []
    for fid in faculty_df['faculty_id']:
        for day in days:
            faculty_availability_data.append({
                'faculty_id': fid, 'day_of_week': day, 'time_slot_start': '09:00',
                'time_slot_end': '17:00', 'availability_type': 'Available'
            })
    faculty_availability_df = pd.DataFrame(faculty_availability_data)
    
    room_availability_df = []
    for rid in rooms_df['room_id']:
        for day in days:
             room_availability_df.append({
                'room_id': rid, 'day_of_week': day, 'time_slot_start': '09:00',
                'time_slot_end': '17:00', 'availability_status': 'Available'
            })
    room_availability_df = pd.DataFrame(room_availability_df)

    # --- Save all to CSV ---
    students_df.to_csv('Students.csv', index=False)
    faculty_df.to_csv('Faculty.csv', index=False)
    rooms_df.to_csv('Rooms.csv', index=False)
    courses_df.to_csv('Courses.csv', index=False)
    curriculum_df.to_csv('Curriculum.csv', index=False)
    student_choices_df.to_csv('Student_Choices.csv', index=False)
    faculty_expertise_df.to_csv('Faculty_Expertise.csv', index=False)
    faculty_availability_df.to_csv('Faculty_Availability.csv', index=False)
    room_availability_df.to_csv('Room_Availability.csv', index=False)
    
    print("  - Generated and saved new mock data CSV files.")

def generate_constraints_json():
    """Generates a single constraints.json file."""
    print("--- Generating constraints.json ---")
    
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    
    constraints = {
        "hard": {
            "faculty_day_off": {
                "enabled": True,
                "scope": {"faculty_ids": ["FAC001"]},
                "params": {"days": ["Friday"]}
            }
        },
        "soft": {
            "avoid_early_slot": {
                "enabled": True,
                "weight": 2.0,
                "params": {
                    "early_slots": [f"{day}_09:00-10:00" for day in days]
                }
            },
            "avoid_last_slot": {
                "enabled": True,
                "weight": 3.0,
                "params": {
                    "last_slot_by_day": [f"{day}_16:00-17:00" for day in days]
                }
            },
            "faculty_back_to_back": {
                "enabled": True,
                "weight": 1.5,
                "params": {"window": 2}
            }
        }
    }
    
    with open('constraints.json', 'w') as f:
        json.dump(constraints, f, indent=2)
        
    print("  - Generated and saved constraints.json.")

if __name__ == '__main__':
    generate_data_csvs()
    generate_constraints_json()
    print("\n--- ✅ Mock data and constraints generation complete. ---")
