import random
import copy
from collections import defaultdict
import pandas as pd
import time

class GeneticAlgorithmTimetable:
    def __init__(self, data, next_slot_map, allowed_slots_by_course=None,
                 population_size=24, generations=14, mutation_rate=0.35, crossover_rate=0.8):
        self.data = data
        self.next_slot_map = next_slot_map
        self.population_size = population_size
        allowed_slots_by_course = allowed_slots_by_course or {}
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.population = []

        # --- Pre-computation for Speed ---
        print("\n--- Pre-computing GA data for optimization ---")
        start_time = time.time()
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
        self.course_candidate_pool = self._precompute_candidate_pool()
        print(f"Pre-computation completed in {time.time() - start_time:.2f} seconds.")

    def _precompute_candidate_pool(self):
        pool = defaultdict(list)
        rooms_df = self.data['rooms']
        time_keys = list(self.data['time_slot_map'].keys())
        for course_id in self.all_course_ids:
            num_students = len(self.course_student_map.get(course_id, []))
            ctype = str(self.courses_df.loc[self.courses_df['course_id'] == course_id, 'course_type'].iloc[0]).lower()
            is_lab = 'lab' in ctype
            suitable_rooms = [
                r['room_id'] for _, r in rooms_df.iterrows()
                if int(r.get('capacity', 0)) >= num_students and
                   (('lab' in str(r.get('room_type','')).lower()) == is_lab)
            ]
            allowed_t = list(self.allowed_slots_by_course.get(course_id, time_keys))
            for f_id in self.expert_map.get(course_id, []):
                for r_id in suitable_rooms:
                    for t_slot in allowed_t:
                        pool[course_id].append((f_id, r_id, t_slot))
        return pool

    def initialize_population(self, initial_schedules):
        print("Initializing a diverse and valid GA population...")
        self.population.append(self.create_valid_individual(initial_schedules[0]))
        while len(self.population) < self.population_size:
            self.population.append(self.create_valid_individual({}))
        print(f"GA population initialized with {len(self.population)} individuals.")

    def create_valid_individual(self, initial_assignments):
        individual = initial_assignments.copy()
        busy_map = self.get_busy_map(individual)
        courses_to_place = [cid for cid in self.all_course_ids if cid not in [k[1] for k in individual.keys()]]
        random.shuffle(courses_to_place)
        for course_id in courses_to_place:
            valid_placements = self.find_valid_placements(course_id, busy_map)
            if valid_placements:
                chosen = random.choice(valid_placements)
                individual[chosen] = True
                self.update_busy_map(busy_map, chosen)
        return individual

    def find_valid_placements(self, course_id, busy_map):
        valid_placements = []
        students = self.course_student_map.get(course_id, [])
        duration = self.course_details_map.get(course_id, 1)
        for (f_id, r_id, t_slot) in self.course_candidate_pool.get(course_id, []):
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
        slots = [start_slot]; current = start_slot
        for _ in range(duration - 1):
            current = self.next_slot_map.get(current)
            if not current: return None
            slots.append(current)
        return slots
        
    def get_busy_map(self, individual):
        busy_map = {'faculty': defaultdict(set), 'room': defaultdict(set), 'student': defaultdict(set)}
        for assignment in individual.keys(): self.update_busy_map(busy_map, assignment)
        return busy_map

    def update_busy_map(self, busy_map, assignment):
        f, c, t, r = assignment
        slots = self.get_required_slots(t, self.course_details_map.get(c, 1))
        if not slots: return
        students = self.course_student_map.get(c, [])
        for s in slots:
            busy_map['faculty'][f].add(s)
            busy_map['room'][r].add(s)
            for sid in students: busy_map['student'][sid].add(s)

    def fitness(self, individual):
        if len(set(k[1] for k in individual.keys())) != len(self.all_course_ids): return -999999
        violations = self.hard_constraint_violations(individual)
        if violations > 0: return -100000 * violations
        return self.student_gap_score(individual)

    def hard_constraint_violations(self, individual):
        violations = 0; busy_map = defaultdict(list)
        for f, c, t, r in individual.keys():
            slots = self.get_required_slots(t, self.course_details_map.get(c, 1))
            if not slots: violations += 1; continue
            students = self.course_student_map.get(c, [])
            for s in slots:
                busy_map[('f', f, s)].append(c); busy_map[('r', r, s)].append(c)
                for sid in students: busy_map[('s', sid, s)].append(c)
        for assignments in busy_map.values(): violations += (len(assignments) - 1)
        return violations

    def select_parents(self):
        participants = random.sample(self.population, 5)
        participants.sort(key=lambda ind: self.fitness(ind), reverse=True)
        return participants[0], participants[1]

    def crossover(self, parent1, parent2):
        """
        --- NEW: Greedy Crossover ---
        Creates a child from the fitter parent, then tries to improve it
        by intelligently incorporating genes from the second parent.
        """
        fitter_parent = parent1 if self.fitness(parent1) >= self.fitness(parent2) else parent2
        weaker_parent = parent2 if self.fitness(parent1) >= self.fitness(parent2) else parent1
        
        child = fitter_parent.copy()
        
        # Try to incorporate better placements from the weaker parent
        for key in weaker_parent:
            course_id = key[1]
            
            # Find the corresponding course in the child
            child_key = next((k for k in child if k[1] == course_id), None)
            if not child_key: continue

            # Create a temporary schedule to test the swap
            temp_child = child.copy()
            del temp_child[child_key] # Remove the old assignment
            
            # Check if the weaker parent's assignment is valid in this new context
            temp_busy_map = self.get_busy_map(temp_child)
            if self.is_placement_valid(key[0], key[3], self.course_student_map.get(course_id, []), self.get_required_slots(key[2], self.course_details_map.get(course_id, 1)), temp_busy_map):
                temp_child[key] = True
                # If the swap improved the score, keep it
                if self.fitness(temp_child) > self.fitness(child):
                    child = temp_child
                    
        return child

    def mutate(self, individual):
        """
        --- NEW: Greedy Mutation ---
        Moves a random course to the BEST possible new slot.
        """
        mutated_individual = individual.copy()
        key_to_mutate = random.choice(list(mutated_individual.keys()))
        course_id = key_to_mutate[1]
        del mutated_individual[key_to_mutate]

        busy_map = self.get_busy_map(mutated_individual)
        valid_placements = self.find_valid_placements(course_id, busy_map)
        
        if valid_placements:
            best_placement = None
            best_fitness = -float('inf')
            
            # Find the placement that results in the highest fitness
            for placement in valid_placements:
                temp_individual = mutated_individual.copy()
                temp_individual[placement] = True
                current_fitness = self.fitness(temp_individual)
                if current_fitness > best_fitness:
                    best_fitness = current_fitness
                    best_placement = placement
            
            if best_placement:
                mutated_individual[best_placement] = True
            else:
                 mutated_individual[key_to_mutate] = True # Put it back
        else:
            mutated_individual[key_to_mutate] = True # Put it back

        return mutated_individual

    def run(self):
        """Runs the GA with an early stopping criterion."""
        if not self.population: return {}
        best_overall = max(self.population, key=self.fitness)
        best_fitness = self.fitness(best_overall)
        patience, no_improvement_gens = 10, 0

        for gen in range(self.generations):
            new_population = [copy.deepcopy(best_overall)]
            while len(new_population) < self.population_size:
                p1, p2 = self.select_parents()
                child = self.crossover(p1, p2)
                if random.random() < self.mutation_rate: child = self.mutate(child)
                new_population.append(child)
            self.population = new_population
            
            current_best = max(self.population, key=self.fitness)
            current_best_fitness = self.fitness(current_best)

            if current_best_fitness > best_fitness:
                best_fitness = current_best_fitness
                best_overall = current_best
                no_improvement_gens = 0
                print(f"Generation {gen + 1}: New Best Fitness = {best_fitness:.4f}")
            else:
                no_improvement_gens += 1
            
            if no_improvement_gens >= patience:
                print(f"Stopping early at generation {gen + 1}.")
                break
        
        print(f"GA Completed: Best Fitness = {best_fitness:.4f}")
        return best_overall

    def student_gap_score(self, individual):
        schedules = defaultdict(lambda: defaultdict(list))
        for _, c, t, _ in individual.keys():
            day = t.split('_')[0]
            for s in self.course_student_map.get(c, []):
                schedules[s][day].append(int(t.split('_')[1].split(':')[0]))
        gaps, days_with_class = 0, 0
        for student, days in schedules.items():
            for day, hours in days.items():
                days_with_class += 1
                if len(hours) > 1:
                    hours.sort()
                    gaps += (hours[-1] - hours[0] + 1) - len(hours)
        avg_gap = gaps / days_with_class if days_with_class > 0 else 0
        return 1 / (avg_gap + 1)