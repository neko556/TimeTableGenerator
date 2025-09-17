import copy
import random
import pandas as pd
from collections import deque, defaultdict

class TabuSearchTimetable:
    def __init__(self, data, next_slot_map, tabu_tenure=10, max_iterations=200):
        self.data = data
        self.next_slot_map = next_slot_map
        self.tabu_list = deque(maxlen=tabu_tenure)
        self.max_iterations = max_iterations

        # --- Pre-compute for speed (mirroring the GA's logic) ---
        self.courses_df = self.data['courses']
        self.student_choices_df = self.data['student_choices']
        
        self.course_student_map = self.student_choices_df.groupby('chosen_course_id')['student_id'].apply(list).to_dict()
        self.expert_map = defaultdict(list)
        for _, row in self.data['faculty_expertise'].iterrows():
            self.expert_map[row['course_id']].append(row['faculty_id'])
        self.course_details_map = pd.Series(
            self.courses_df.duration_hours.values, 
            index=self.courses_df.course_id
        ).to_dict()

    # --- Core Validity and Fitness Functions (Identical to GA) ---

    def get_required_slots(self, start_slot, duration):
        """Gets a list of all slots for a class, or None if not possible."""
        slots = [start_slot]
        current_slot = start_slot
        for _ in range(duration - 1):
            next_slot = self.next_slot_map.get(current_slot)
            if not next_slot: return None
            slots.append(next_slot)
            current_slot = next_slot
        return slots

    def get_busy_map(self, individual):
        """Builds a duration-aware busy map for all resources."""
        busy_map = {'faculty': defaultdict(set), 'room': defaultdict(set), 'student': defaultdict(set)}
        for f_id, c_id, t_slot, r_id in individual.keys():
            duration = self.course_details_map.get(c_id, 1)
            required_slots = self.get_required_slots(t_slot, duration)
            if not required_slots: continue
            students = self.course_student_map.get(c_id, [])
            for slot in required_slots:
                busy_map['faculty'][f_id].add(slot)
                busy_map['room'][r_id].add(slot)
                for s_id in students:
                    busy_map['student'][s_id].add(slot)
        return busy_map

    def hard_constraint_violations(self, individual):
        """The single source of truth for schedule validity."""
        violations = 0
        busy_map = defaultdict(list)
        for f_id, c_id, t_slot, r_id in individual.keys():
            duration = self.course_details_map.get(c_id, 1)
            required_slots = self.get_required_slots(t_slot, duration)
            if not required_slots: 
                violations += 1; continue
            students = self.course_student_map.get(c_id, [])
            for slot in required_slots:
                busy_map[('faculty', f_id, slot)].append(c_id)
                busy_map[('room', r_id, slot)].append(c_id)
                for s_id in students:
                    busy_map[('student', s_id, slot)].append(c_id)
        for assignments in busy_map.values():
            violations += (len(assignments) - 1)
        return -100000 * violations if violations > 0 else 0
    
    def student_gap_score(self, individual):
        """Calculates the soft constraint score for student gaps."""
        student_schedules = defaultdict(lambda: defaultdict(list))
        for _, c_id, t_slot, _ in individual.keys():
            day = t_slot.split('_')[0]
            for s_id in self.course_student_map.get(c_id, []):
                student_schedules[s_id][day].append(int(t_slot.split('_')[1].split(':')[0]))
        
        total_gap_hours, total_student_days = 0, 0
        for student, days in student_schedules.items():
            for day, hours in days.items():
                total_student_days += 1
                if len(hours) > 1:
                    hours.sort()
                    duration = (hours[-1] - hours[0]) + 1
                    total_gap_hours += (duration - len(hours))
        
        average_gap = total_gap_hours / total_student_days if total_student_days > 0 else 0
        return 1 / (average_gap + 1)
        
    def fitness(self, individual):
        """The main fitness function, identical to the GA's."""
        penalty = self.hard_constraint_violations(individual)
        if penalty < 0:
            return penalty
        return self.student_gap_score(individual)
        
    # --- Tabu Search Specific Logic ---

    def neighborhood(self, solution):
        """
        Intelligent neighborhood generation: Finds all valid moves for a single course.
        """
        neighbors = []
        # Create a list of all course assignments (keys) to choose from
        all_assignments = list(solution.keys())
        if not all_assignments:
            return []

        # Pick one random assignment to change
        key_to_move = random.choice(all_assignments)
        course_id_to_move = key_to_move[1]
        
        # Create a temporary solution without this course to find open slots
        temp_solution = solution.copy()
        del temp_solution[key_to_move]
        
        # Build a busy map based on the temporary solution
        busy_map = self.get_busy_map(temp_solution)
        
        # Find all other valid places this course could go
        # (This reuses the powerful logic from the GA)
        students = self.course_student_map.get(course_id_to_move, [])
        duration = self.course_details_map.get(course_id_to_move, 1)

        for f_id in self.expert_map.get(course_id_to_move, []):
            for r_id in self.data['rooms']['room_id']:
                for t_slot in self.data['time_slot_map'].keys():
                    required_slots = self.get_required_slots(t_slot, duration)
                    if not required_slots: continue
                    
                    is_valid = True
                    for slot in required_slots:
                        if slot in busy_map['faculty'].get(f_id, set()) or \
                           slot in busy_map['room'].get(r_id, set()) or \
                           any(slot in busy_map['student'].get(s_id, set()) for s_id in students):
                            is_valid = False; break
                    
                    if is_valid:
                        # Create a new neighbor solution for this valid move
                        new_neighbor = temp_solution.copy()
                        new_neighbor[(f_id, course_id_to_move, t_slot, r_id)] = True
                        neighbors.append(new_neighbor)
                        
        return neighbors
    
    def run(self, initial_solution):
        """
        Run Tabu Search starting from the GA's best solution.
        """
        # Ensure the initial solution is a dictionary
        if not isinstance(initial_solution, dict):
            print("Tabu Error: Initial solution is not in the correct format.")
            return initial_solution

        current_solution = copy.deepcopy(initial_solution)
        best_solution = current_solution
        best_fitness = self.fitness(best_solution)

        if best_fitness < 0:
            print("Warning: Tabu search was given an invalid initial solution. It will try to repair it.")
        
        for iteration in range(self.max_iterations):
            neighborhood = self.neighborhood(current_solution)
            
            # Filter out neighbors that are in the tabu list
            # We convert the dict to a frozenset of items to make it hashable for the tabu list
            neighborhood = [n for n in neighborhood if frozenset(n.items()) not in self.tabu_list]
            
            if not neighborhood:
                # If no non-tabu moves, we are stuck. Could add more complex logic here.
                break 
            
            neighbor_fitness_pairs = [(self.fitness(n), n) for n in neighborhood]
            neighbor_fitness_pairs.sort(key=lambda x: x[0], reverse=True)
            
            best_neighbor_fitness, best_neighbor = neighbor_fitness_pairs[0]
            
            # Aspiration Criterion: if this move leads to the best-ever solution,
            # accept it even if it's tabu (already handled by how we find best_neighbor)
            if best_neighbor_fitness > best_fitness:
                best_solution = best_neighbor
                best_fitness = best_neighbor_fitness
            
            # Move to the best neighbor for the next iteration
            current_solution = best_neighbor
            
            # Add the state of the new solution to the tabu list
            self.tabu_list.append(frozenset(current_solution.items()))
            
            if iteration % 10 == 0:
                print(f"Tabu Iteration {iteration+1}: Best Fitness = {best_fitness:.4f}")
        
        print("Tabu Search completed.")
        return best_solution