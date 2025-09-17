import random
import copy
from collections import defaultdict
import pandas as pd

class GeneticAlgorithmTimetable:
    def __init__(self, data, next_slot_map, population_size=100, generations=150, mutation_rate=0.2, crossover_rate=0.8):
        self.data = data
        self.next_slot_map = next_slot_map
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.population = []

        # --- Pre-compute for speed ---
        self.courses_df = self.data['courses']
        self.all_course_ids = self.courses_df['course_id'].tolist()
        self.course_student_map = self.data['student_choices'].groupby('chosen_course_id')['student_id'].apply(list).to_dict()
        self.expert_map = defaultdict(list)
        for _, row in self.data['faculty_expertise'].iterrows():
            self.expert_map[row['course_id']].append(row['faculty_id'])
        self.course_details_map = pd.Series(
            self.courses_df.duration_hours.values,
            index=self.courses_df.course_id
        ).to_dict()

    def initialize_population(self, initial_schedules):
        """Initializes a population with the SAT-seeded solution and other valid random solutions."""
        print("Initializing a diverse and valid GA population...")
        sat_seed_schedule = initial_schedules[0]
        
        seeded_individual = self.create_valid_individual(sat_seed_schedule)
        self.population.append(seeded_individual)

        while len(self.population) < self.population_size:
            random_individual = self.create_valid_individual({})
            if len(random_individual) == len(self.all_course_ids):
                self.population.append(random_individual)
        
        if not self.population:
             raise ValueError("Could not create any valid individuals. The problem is likely too constrained.")
        print(f"GA population initialized with {len(self.population)} complete and valid individuals.")

    def create_valid_individual(self, initial_assignments):
        """Creates a single, complete, and valid schedule."""
        individual = initial_assignments.copy()
        busy_map = self.get_busy_map(individual)
        
        courses_to_place = [cid for cid in self.all_course_ids if cid not in [k[1] for k in individual.keys()]]
        random.shuffle(courses_to_place)

        for course_id in courses_to_place:
            valid_placements = self.find_valid_placements(course_id, busy_map)
            if valid_placements:
                chosen_placement = random.choice(valid_placements)
                individual[chosen_placement] = True
                self.update_busy_map(busy_map, chosen_placement)
        return individual

    def find_valid_placements(self, course_id, busy_map):
        valid_placements = []
        students = self.course_student_map.get(course_id, [])
        duration = self.course_details_map.get(course_id, 1)
        for f_id in self.expert_map.get(course_id, []):
            for r_id in self.data['rooms']['room_id']:
                for t_slot in self.data['time_slot_map'].keys():
                    required_slots = self.get_required_slots(t_slot, duration)
                    if required_slots and self.is_placement_valid(f_id, r_id, students, required_slots, busy_map):
                        valid_placements.append((f_id, course_id, t_slot, r_id))
        return valid_placements

    def is_placement_valid(self, f_id, r_id, students, required_slots, busy_map):
        for slot in required_slots:
            if slot in busy_map['faculty'].get(f_id, set()) or \
               slot in busy_map['room'].get(r_id, set()) or \
               any(slot in busy_map['student'].get(s_id, set()) for s_id in students):
                return False
        return True

    def get_required_slots(self, start_slot, duration):
        slots = [start_slot]
        current_slot = start_slot
        for _ in range(duration - 1):
            next_slot = self.next_slot_map.get(current_slot)
            if not next_slot: return None
            slots.append(next_slot)
            current_slot = next_slot
        return slots
        
    def get_busy_map(self, individual):
        busy_map = {'faculty': defaultdict(set), 'room': defaultdict(set), 'student': defaultdict(set)}
        for assignment in individual.keys():
            self.update_busy_map(busy_map, assignment)
        return busy_map

    def update_busy_map(self, busy_map, assignment):
        f_id, c_id, t_slot, r_id = assignment
        duration = self.course_details_map.get(c_id, 1)
        required_slots = self.get_required_slots(t_slot, duration)
        if not required_slots: return
        students = self.course_student_map.get(c_id, [])
        for slot in required_slots:
            busy_map['faculty'][f_id].add(slot)
            busy_map['room'][r_id].add(slot)
            for s_id in students:
                busy_map['student'][s_id].add(slot)

    def fitness(self, individual):
        """The definitive fitness function: checks completeness, then clashes, then soft constraints."""
        # 1. HARD CONSTRAINT: Completeness
        num_scheduled = len(set(k[1] for k in individual.keys()))
        num_total = len(self.all_course_ids)
        if num_scheduled != num_total:
            return -1000000 * (num_total - num_scheduled)

        # 2. HARD CONSTRAINT: Clashes
        violations = self.hard_constraint_violations(individual)
        if violations > 0:
            return -100000 * violations
        
        # 3. SOFT CONSTRAINTS (only if fully valid)
        return self.student_gap_score(individual)

    def hard_constraint_violations(self, individual):
        """Returns the total number of clashes."""
        violations = 0
        busy_map = defaultdict(list)
        for f_id, c_id, t_slot, r_id in individual.keys():
            duration = self.course_details_map.get(c_id, 1)
            required_slots = self.get_required_slots(t_slot, duration)
            if not required_slots: violations += 1; continue
            students = self.course_student_map.get(c_id, [])
            for slot in required_slots:
                busy_map[('faculty', f_id, slot)].append(c_id)
                busy_map[('room', r_id, slot)].append(c_id)
                for s_id in students:
                    busy_map[('student', s_id, slot)].append(c_id)
        for assignments in busy_map.values():
            violations += (len(assignments) - 1)
        return violations

    def select_parents(self):
        """Uses robust Tournament Selection."""
        participants = random.sample(self.population, 5)
        participants.sort(key=lambda ind: self.fitness(ind), reverse=True)
        return participants[0], participants[1]

    def crossover(self, parent1, parent2):
        """A simple but safe crossover that creates a new valid individual."""
        return self.create_valid_individual({})

    def mutate(self, individual):
        """Moves ANY random course to a new valid slot."""
        mutated_individual = individual.copy()
        key_to_mutate = random.choice(list(mutated_individual.keys()))
        course_id = key_to_mutate[1]
        del mutated_individual[key_to_mutate]

        busy_map = self.get_busy_map(mutated_individual)
        valid_placements = self.find_valid_placements(course_id, busy_map)
        
        if valid_placements:
            mutated_individual[random.choice(valid_placements)] = True
        else:
            mutated_individual[key_to_mutate] = True # Put it back
        return mutated_individual

    def run(self):
        best_overall_individual = self.population[0]
        best_overall_fitness = self.fitness(best_overall_individual)
        patience, gens_no_improvement = 7, 0

        for generation in range(self.generations):
            new_population = [copy.deepcopy(best_overall_individual)]
            while len(new_population) < self.population_size:
                parent1, parent2 = self.select_parents()
                child = self.crossover(parent1, parent2)
                if random.random() < self.mutation_rate:
                    child = self.mutate(child)
                new_population.append(child)

            self.population = new_population
            
            current_best_fitness = max(self.fitness(ind) for ind in self.population)

            if current_best_fitness > best_overall_fitness:
                best_overall_fitness = current_best_fitness
                best_overall_individual = max(self.population, key=self.fitness)
                gens_no_improvement = 0
                print(f"Generation {generation + 1}: New Best Fitness = {best_overall_fitness:.4f}")
            else:
                gens_no_improvement += 1
            
            if gens_no_improvement >= patience:
                print(f"Stopping early at generation {generation + 1}.")
                break

        print(f"GA Completed: Best Fitness = {best_overall_fitness:.4f}")
        return best_overall_individual

    def student_gap_score(self, individual):
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