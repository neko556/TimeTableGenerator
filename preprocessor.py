import pandas as pd
import numpy as np
import math
from collections import defaultdict
from typing import Tuple, Dict, List, Any



def assemble_data(
    data: Dict[str, Any] | None = None,
    with_time_maps: bool = True
) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, List[str]], Dict[str, List[str]], Dict[str, List[str]], Dict[str, List[str]], Dict[str, Any]]:
   

    # 1) Run the existing pipeline to get data + core structures
    if data is None:
        data_full, core_batches, core_batch_sessions = run_preprocessing_pipeline()
    else:
        # If a data dict is supplied, let the pipeline operate on it (reloading if needed)
        # Your current run_preprocessing_pipeline() signature takes no args; reuse its behavior here.
        data_full, core_batches, core_batch_sessions = run_preprocessing_pipeline()

    # 2) Electives via your existing helper
    elective_groups, elective_group_sessions = build_elective_groups_from_data(data_full)

    # 3) Time maps
    time_slot_map, next_slot_map = {}, {}
    if with_time_maps:
        try:
            # Import locally to avoid hard dependency if some scripts don't need it
            from time_slots import generate_time_slots
            z,time_slot_map, next_slot_map = generate_time_slots()
        except Exception as e:
            print(f"[warn] Failed to generate time slots: {e}. Proceeding with empty maps.")
            time_slot_map, next_slot_map = {}, {}

    # 4) Return in the canonical order many callers expect
    return (
        time_slot_map,
        next_slot_map,
        core_batches,
        core_batch_sessions,
        elective_groups,
        elective_group_sessions,
        data_full,
    )
def build_elective_groups_from_data(data, elective_credits=3):
    # Ensure required frames exist; if not, reload from CSVs
    if 'courses' not in data or data['courses'] is None:
        data['courses'] = pd.read_csv('Courses.csv')
    if 'student_choices' not in data or data['student_choices'] is None:
        data['student_choices'] = pd.read_csv('Student_Choices.csv')

    courses_df = data['courses']
    choices_df = data['student_choices']

    # Elective courses only
    elective_mask = courses_df['is_elective'] == True
    elective_courses = courses_df[elective_mask].copy()

    elective_groups = {}
    elective_group_sessions = {}

    # Group students by their chosen elective course
    chosen = choices_df[choices_df['chosen_course_id'].isin(elective_courses['course_id'])]
    for course_id, grp in chosen.groupby('chosen_course_id'):
        gname = f"Elective_{course_id}"
        members = grp['student_id'].astype(str).tolist()
        elective_groups[gname] = members

        # Determine number of sessions
        row = elective_courses[elective_courses['course_id'] == course_id].iloc[0]
        is_lab = 'lab' in str(row.get('course_type', '')).lower()
        credits = int(row.get('credits', elective_credits))
        n_sessions = credits if not is_lab else 1  # labs are modeled as 1 double-duration session
        elective_group_sessions[gname] = [f"{course_id}_S{s}" for s in range(1, n_sessions + 1)]

    return elective_groups, elective_group_sessions


def _load_and_clean_data():
    """Internal function to load and clean all required CSV files."""
    print("--- Loading and Validating Data ---")
    
    def safe_read_csv(filename):
        try: return pd.read_csv(filename)
        except FileNotFoundError: print(f"  - FATAL ERROR: '{filename}' not found."); exit()

    data = {
        'students': safe_read_csv('Students.csv'), 'faculty': safe_read_csv('Faculty.csv'),
        'courses': safe_read_csv('Courses.csv'), 'rooms': safe_read_csv('Rooms.csv'),
        'student_choices': safe_read_csv('Student_Choices.csv'),
        'faculty_expertise': safe_read_csv('Faculty_Expertise.csv'),
        'faculty_availability': safe_read_csv('Faculty_Availability.csv'),
        'room_availability': safe_read_csv('Room_Availability.csv'),
        'course_baskets': safe_read_csv('Course_Baskets.csv'),
        'basket_courses': safe_read_csv('Basket_Courses.csv'),
    }
    for df in data.values():
        for col in ['student_id', 'course_id', 'chosen_course_id', 'faculty_id', 'basket_id', 'program_id']:
            if col in df.columns: df[col] = df[col].astype(str).str.strip()
    print("  - Data loaded and cleaned successfully.")
    return data

def _create_lab_batches(data):
    """Internal function to split lab courses into smaller sections."""
    print("\n--- Stage 1: Creating Lab Batches ---")
    courses_df, choices_df, expertise_df = data['courses'].copy(), data['student_choices'].copy(), data['faculty_expertise'].copy()
    
    # --- FIX: Only split courses that are NOT electives ---
    is_lab_mask = courses_df['course_type'].str.contains('lab', case=False, na=False)
    courses_to_split = courses_df[is_lab_mask & courses_df['max_size'].notna() & (courses_df['max_size'] > 0)]

    for _, course in courses_to_split.iterrows():
        course_id, max_size = course['course_id'], int(course['max_size'])
        enrolled = choices_df[choices_df['chosen_course_id'] == course_id]
        if enrolled.empty: continue
        
        num_batches = math.ceil(len(enrolled) / max_size)
        if num_batches > 1:
            print(f"  - Splitting '{course_id}' ({len(enrolled)} students) into {num_batches} sections.")
            original_experts = expertise_df[expertise_df['course_id'] == course_id]
            courses_df = courses_df[courses_df['course_id'] != course_id]
            choices_df = choices_df[choices_df['chosen_course_id'] != course_id]
            expertise_df = expertise_df[expertise_df['course_id'] != course_id]
            
            student_chunks = np.array_split(enrolled, num_batches)
            for i, chunk in enumerate(student_chunks):
                new_id = f"{course_id}-{chr(ord('A') + i)}"
                new_course = course.copy(); new_course['course_id'] = new_id
                courses_df = pd.concat([courses_df, new_course.to_frame().T], ignore_index=True)
                
                updated_choices = chunk.copy(); updated_choices['chosen_course_id'] = new_id
                choices_df = pd.concat([choices_df, updated_choices], ignore_index=True)
                
                if not original_experts.empty:
                    new_experts = original_experts.copy(); new_experts['course_id'] = new_id
                    expertise_df = pd.concat([expertise_df, new_experts], ignore_index=True)
    
    data['courses'], data['student_choices'], data['faculty_expertise'] = courses_df, choices_df, expertise_df
    return data

def _determine_optimal_batch_size(data, min_size=20, max_size=60):
    """Internal function to determine an optimal batch size."""
    print("\n--- Determining Optimal Batch Size ---")
    rooms_df = data['rooms']
    non_lab_rooms = rooms_df[~rooms_df['room_type'].str.contains("lab", case=False, na=False)]
    max_cap = non_lab_rooms['capacity'].max() if not non_lab_rooms.empty else max_size
    optimal_size = int(max(min_size, min(max_cap, max_size)))
    print(f"  - Calculated Optimal Batch Size: {optimal_size}")
    return optimal_size

def create_core_batches_and_sessions(data, optimal_batch_size):
    """
    Creates core student batches and defines the SESSIONS for their core curriculum ONLY.
    """
    print("\n--- Creating Core Batches and Defining Course Sessions ---")
    students_df, courses_df = data['students'], data['courses']
    course_baskets, basket_courses = data['course_baskets'], data['basket_courses']
    
    core_batches, core_batch_sessions = {}, {}
    
    # --- Get all non-elective courses first ---
    all_core_course_ids = courses_df[courses_df['is_elective'] == False]['course_id'].tolist()
    
    # Map baskets to only the core courses within them
    basket_to_courses = defaultdict(list)
    for _, row in basket_courses.iterrows():
        if row['course_id'] in all_core_course_ids:
            basket_to_courses[row['basket_id']].append(row['course_id'])

    program_groups = students_df.groupby(['program_id', 'current_semester'])
    for (prog_id, sem), group in program_groups:
        students = group['student_id'].tolist();
        if not students: continue
        
        basket = course_baskets[(course_baskets['program_id'] == prog_id) & (course_baskets['semester'] == sem)]
        if basket.empty: continue
        basket_id = basket['basket_id'].iloc[0]

        num_sub_batches = math.ceil(len(students) / optimal_batch_size)
        print(f"  - Splitting {prog_id}_Sem{sem} ({len(students)} students) into {num_sub_batches} batches.")
        student_chunks = np.array_split(students, num_sub_batches)

        for i, chunk in enumerate(student_chunks):
            batch_name = f"{prog_id}_Sem{sem}-{chr(ord('A') + i)}"
            core_batches[batch_name] = list(chunk)
            sessions = []
            for cid in basket_to_courses.get(basket_id, []):
                course_info_row = courses_df[courses_df['course_id'] == cid]
                if course_info_row.empty: continue
                
                course_info = course_info_row.iloc[0]
                is_lab = 'lab' in str(course_info.get('course_type', '')).lower()
                
                if is_lab:
                    num_sessions = 1
                else:
                    num_sessions = int(course_info.get('credits', 1))
                
                for s_num in range(1, num_sessions + 1):
                    sessions.append(f"{cid}_S{s_num}")
            core_batch_sessions[batch_name] = sessions

    print(f"  - Created {len(core_batches)} core batches with session lists.")
    return data, core_batches, core_batch_sessions

def run_preprocessing_pipeline():
    """The main public function to orchestrate all preprocessing steps."""
    data = _load_and_clean_data()
    data = _create_lab_batches(data)
    optimal_batch_size = _determine_optimal_batch_size(data)
    data, core_batches, core_batch_sessions = create_core_batches_and_sessions(data, optimal_batch_size)
    return data, core_batches, core_batch_sessions