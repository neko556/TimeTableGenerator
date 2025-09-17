import pandas as pd
import random
from faker import Faker

# --- Configuration ---
NUM_STUDENTS = 200
NUM_FACULTY = 25 # Slightly more faculty
NUM_COURSES = 40
NUM_ROOMS = 15
# --- FIX: Increase faculty availability to make the problem less constrained ---
FACULTY_SLOTS_PER_WEEK = 15 # Was 10, increased to provide more scheduling flexibility

fake = Faker('en_IN')

def find_course_combination(courses, target_credits):
    """
    A helper function to find a subset of courses that sums to the target credit amount.
    """
    course_list = list(courses.items())
    
    def find_sum(path, current_sum, start_index):
        if current_sum == target_credits:
            return path
        if current_sum > target_credits or start_index == len(course_list):
            return None
        course_id, credits = course_list[start_index]
        solution = find_sum(path + [course_id], current_sum + credits, start_index + 1)
        if solution:
            return solution
        solution = find_sum(path, current_sum, start_index + 1)
        if solution:
            return solution
        return None

    random.shuffle(course_list)
    return find_sum([], 0, 0)

def generate_full_dataset():
    """
    Generates a complete, interconnected set of CSV files for the timetabling system.
    """
    print("Generating large, complete dataset...")

    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'] # Added Saturday
    hours = [f"{h:02d}:00" for h in range(10, 18)] # Extended hours
    possible_slots = [{'day': day, 'start': hours[i], 'end': hours[i+1]} for day in days for i in range(len(hours) - 1) if hours[i] != "12:00"]
    
    students_df = pd.DataFrame([{'student_id': f'STU{i:04d}', 'program_id': 'BE-IT', 'current_semester': 1} for i in range(1, NUM_STUDENTS + 1)])
    faculty_df = pd.DataFrame([{'faculty_id': f'FAC{i:03d}'} for i in range(1, NUM_FACULTY + 1)])
    rooms_data = [{'room_id': f'ROOM{i:03d}', 'room_type': 'Lab' if i % 4 == 0 else 'Classroom', 'capacity': random.randint(25, 35) if i % 4 == 0 else random.randint(50, 100)} for i in range(1, NUM_ROOMS + 1)]
    rooms_df = pd.DataFrame(rooms_data)

    courses_data = []
    for i in range(1, NUM_COURSES + 1):
        is_lab = i % 8 == 0
        is_elective = i % 10 == 0
        courses_data.append({
            'course_id': f'CRS{i:03d}',
            'course_type': 'Lab' if is_lab else 'Elective' if is_elective else 'Core',
            'credits': random.choice([3, 4]),
            'duration_hours': 2 if is_lab else 1,
            'max_size': random.randint(25, 35) if is_lab else random.randint(80, 100),
            'is_elective': is_elective
        })
    courses_df = pd.DataFrame(courses_data)
    
    all_course_ids = courses_df['course_id'].tolist()

    print("Generating guaranteed valid student course choices...")
    student_choices_data = []
    choice_id = 1
    course_credits_map = pd.Series(courses_df.credits.values, index=courses_df.course_id).to_dict()
    required_credits = 18

    for sid in students_df['student_id']:
        my_courses = find_course_combination(course_credits_map, required_credits)
        if my_courses is None:
            print(f"Warning: Could not find a course combination for student {sid}. Skipping.")
            continue
        for cid in my_courses:
            student_choices_data.append({'choice_id': choice_id, 'student_id': sid, 'basket_id': 'BASKET_MAIN', 'chosen_course_id': cid})
            choice_id += 1
    student_choices_df = pd.DataFrame(student_choices_data)
    
    expertise_data, exp_id = [], 1
    for cid in all_course_ids:
        # --- FIX: Ensure more experts are available ---
        num_experts = random.randint(2, 4) # Was 1, 3
        experts = random.sample(faculty_df['faculty_id'].tolist(), num_experts)
        for fid in experts:
            expertise_data.append({'expertise_id': exp_id, 'faculty_id': fid, 'course_id': cid})
            exp_id += 1
    faculty_expertise_df = pd.DataFrame(expertise_data)

    faculty_availability_data, avail_id = [], 1
    for fid in faculty_df['faculty_id']:
        for slot in random.sample(possible_slots, FACULTY_SLOTS_PER_WEEK):
            faculty_availability_data.append({'availability_id': avail_id, 'faculty_id': fid, 'day_of_week': slot['day'], 'time_slot_start': slot['start'], 'time_slot_end': slot['end'], 'availability_type': "Available"})
            avail_id += 1
    faculty_availability_df = pd.DataFrame(faculty_availability_data)
    
    room_availability_data, ravail_id = [], 1
    for rid in rooms_df['room_id']:
        for day in days:
            room_availability_data.append({'availability_id': ravail_id, 'room_id': rid, 'day_of_week': day, 'time_slot_start': '10:00', 'time_slot_end': '18:00', 'availability_status': 'Available'})
            ravail_id += 1
    room_availability_df = pd.DataFrame(room_availability_data)
    
    course_baskets_df = pd.DataFrame([{'basket_id': 'BASKET_MAIN', 'program_id': 'BE-IT', 'semester': 1, 'required_credits': 18}])
    basket_courses_df = pd.DataFrame({'id': range(1, NUM_COURSES + 1), 'basket_id': 'BASKET_MAIN', 'course_id': all_course_ids})
    scheduling_constraints_df = pd.DataFrame([{'constraint_id': 1, 'description': 'Default'}])
    
    # --- Save all to CSV ---
    # (Save commands remain the same)
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
    scheduling_constraints_df.to_csv('Scheduling_Constraints.csv', index=False)
    
    print(f"Generated {NUM_STUDENTS} students, {NUM_FACULTY} faculty, {NUM_COURSES} courses, and {len(student_choices_df)} registrations.")

if __name__ == '__main__':
    generate_full_dataset()