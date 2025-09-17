# ga_solver.py

import random
import copy
from collections import defaultdict
import pandas as pd
import time

class GeneticAlgorithmTimetable:
    """
    Fast GA on a scoped set of sessions (sid_scope), with fixed sessions as occupancy.
    - No faculty preferences; soft = student compactness.
    - Feasible operators; durations clamped to 1 (post-opt).
    - Allowed windows include seed time fallback to avoid empty pools.
    """

    def __init__(self, data, next_slot_map,
                 population_size=24, generations=10,
                 mutation_rate=0.35, crossover_rate=0.8,
                 sid_scope=None,
                 sid_to_course=None,
                 fixed_assignments=None,            # list[(f,sid,t,r)]
                 allowed_slots_by_sid=None,         # dict sid -> set(time)
                 seed_schedule=None):               # dict {(f,sid,t,r): True}
        self.data = data
        self.next_slot_map = next_slot_map
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.population = []

        self.sid_scope = list(sid_scope or [])
        self.sid_to_course = dict(sid_to_course or {})
        self.fixed_assignments = list(fixed_assignments or [])
        self.allowed_slots_by_sid = allowed_slots_by_sid or {}
        self.seed_schedule = dict(seed_schedule or {})

        print("\n--- Pre-computing GA data for optimization ---")
        t0 = time.time()
        self.courses_df = self.data['courses']
        base = pd.Series(1, index=self.courses_df.index)  # clamp to 1 slot
        self.course_details_map = pd.Series(base.values, index=self.courses_df['course_id']).to_dict()
        sc = self.data['student_choices']
        self.course_student_map = sc.groupby('chosen_course_id')['student_id'].apply(list).to_dict()
        self.expert_map = defaultdict(list)
        for _, row in self.data['faculty_expertise'].iterrows():
            self.expert_map[row['course_id']].append(row['faculty_id'])
        self.data['time_slot_map'] = self.data.get('time_slot_map', {})
        self.time_keys = list(self.data['time_slot_map'].keys())
        self.all_sids = sorted(self.sid_scope) if self.sid_scope else []
        self.fixed_busy_map = self._busy_from_fixed(self.fixed_assignments)
        # seed fallback window
        for (f, sid, t, r) in self.seed_schedule.keys():
            self.allowed_slots_by_sid.setdefault(sid, set()).add(t)
        self.sid_candidate_pool = {}
        print(f"Pre-computation completed in {time.time()-t0:.2f} seconds.")

    def _course(self, sid):  # sid -> course_id
        return self.sid_to_course.get(sid, sid)

    def _busy_from_fixed(self, fixed):
        busy = {'faculty': defaultdict(set), 'room': defaultdict(set), 'student': defaultdict(set)}
        for f, sid, t, r in fixed:
            c = self._course(sid)
            students = self.course_student_map.get(c, [])
            busy['faculty'][f].add(t); busy['room'][r].add(t)
            for sid_stu in students: busy['student'][sid_stu].add(t)
        return busy

    def _precompute_candidate_pool(self):
        pool = defaultdict(list)
        rooms_df = self.data['rooms']
        for sid in self.all_sids:
            c = self._course(sid)
            n = len(self.course_student_map.get(c, []))
            row = self.courses_df.loc[self.courses_df['course_id'] == c]
            ctype = str(row['course_type'].iloc[0]).lower() if len(row) else ''
            is_lab = 'lab' in ctype
            suitable = []
            for _, r in rooms_df.iterrows():
                rtype = str(r.get('room_type', '')).lower()
                cap = int(r.get('capacity', 0))
                if cap >= n and (('lab' in rtype) == is_lab):
                    suitable.append(r['room_id'])
            allowed_t = list(self.allowed_slots_by_sid.get(sid, self.time_keys))
            for f_id in self.expert_map.get(c, []):
                for r_id in suitable:
                    for t_slot in allowed_t:
                        pool[sid].append((f_id, sid, t_slot, r_id))
        return pool

    def initialize_population(self, initial_schedules):
        print("Initializing a diverse and valid GA population...")
        seed = initial_schedules[0] if initial_schedules else {}
        if not self.all_sids:
            self.all_sids = sorted({k[1] for k in seed.keys()})
        if not self.all_sids:
            self.population = [seed]; print("GA: Empty scope."); return
        self.sid_candidate_pool = self._precompute_candidate_pool()
        filtered_seed = {k: True for k in seed.keys() if k[1] in set(self.all_sids)}
        self.population = [self.create_valid_individual(filtered_seed)]
        while len(self.population) < self.population_size:
            self.population.append(self.create_valid_individual({}))
        print(f"GA population initialized with {len(self.population)} individuals.")

    # feasibility
    def get_required_slots(self, start_slot, duration): return [start_slot]

    def get_busy_map(self, individual):
        busy = {'faculty': defaultdict(set), 'room': defaultdict(set), 'student': defaultdict(set)}
        for res, d in self.fixed_busy_map.items():
            for k, v in d.items(): busy[res][k] |= set(v)
        for (f, sid, t, r) in individual.keys():
            c = self._course(sid)
            students = self.course_student_map.get(c, [])
            busy['faculty'][f].add(t); busy['room'][r].add(t)
            for sid_stu in students: busy['student'][sid_stu].add(t)
        return busy

    def update_busy_map(self, busy_map, assignment):
        f, sid, t, r = assignment
        c = self._course(sid)
        students = self.course_student_map.get(c, [])
        busy_map['faculty'][f].add(t); busy_map['room'][r].add(t)
        for sid_stu in students: busy_map['student'][sid_stu].add(t)

    def is_placement_valid(self, f_id, r_id, students, slots, busy_map):
        s = slots[0]
        if s in busy_map['faculty'].get(f_id, set()): return False
        if s in busy_map['room'].get(r_id, set()): return False
        if any(s in busy_map['student'].get(sid, set()) for sid in students): return False
        return True

    def find_valid_placements(self, sid, busy_map):
        vs = []
        c = self._course(sid)
        students = self.course_student_map.get(c, [])
        for (f_id, _, t_slot, r_id) in self.sid_candidate_pool.get(sid, []):
            if self.is_placement_valid(f_id, r_id, students, [t_slot], busy_map):
                vs.append((f_id, sid, t_slot, r_id))
        return vs

    def create_valid_individual(self, initial_assignments):
        individual = {}
        for k in initial_assignments.keys():
            if k[1] in set(self.all_sids):
                individual[k] = True
        busy_map = self.get_busy_map(individual)
        placed = {k[1] for k in individual.keys()}
        to_place = [sid for sid in self.all_sids if sid not in placed]
        random.shuffle(to_place)
        for sid in to_place:
            cands = self.find_valid_placements(sid, busy_map)
            if cands:
                pick = random.choice(cands)
                individual[pick] = True
                self.update_busy_map(busy_map, pick)
        return individual

    # objective
    def hard_constraint_violations(self, individual):
        ledger = defaultdict(int)
        for f, sid, t, r in self.fixed_assignments:
            c = self._course(sid)
            ledger[('f', f, t)] += 1; ledger[('r', r, t)] += 1
            for sid_stu in self.course_student_map.get(c, []): ledger[('s', sid_stu, t)] += 1
        for f, sid, t, r in individual.keys():
            c = self._course(sid)
            ledger[('f', f, t)] += 1; ledger[('r', r, t)] += 1
            for sid_stu in self.course_student_map.get(c, []): ledger[('s', sid_stu, t)] += 1
        v = 0
        for cnt in ledger.values():
            if cnt > 1: v += (cnt - 1)
        return v

    def student_gap_score(self, individual):
        schedules = defaultdict(lambda: defaultdict(list))
        for _, sid, t, _ in individual.keys():
            c = self._course(sid)
            day = str(t).split('_', 1)[0]
            hour = int(str(t).split('_', 1)[1].split(':')[0])
            for s in self.course_student_map.get(c, []):
                schedules[s][day].append(hour)
        gaps, days = 0, 0
        for _, days_map in schedules.items():
            for _, hours in days_map.items():
                days += 1
                if len(hours) > 1:
                    hours.sort()
                    gaps += (hours[-1] - hours[0] + 1) - len(hours)
        avg_gap = gaps / days if days > 0 else 0.0
        return 1.0 / (1.0 + avg_gap)

    def fitness(self, individual):
        placed = {k[1] for k in individual.keys()}
        missing = len(self.all_sids) - len(placed)
        v = self.hard_constraint_violations(individual)
        penalty = -1000.0 * v - 100.0 * missing
        return penalty + self.student_gap_score(individual)

    # operators
    def select_parents(self):
        k = min(3, len(self.population))
        P = random.sample(self.population, k)
        P.sort(key=lambda ind: self.fitness(ind), reverse=True)
        return P[0], P[-1] if len(P) > 1 else P[0]

    def crossover(self, p1, p2):
        best = p1 if self.fitness(p1) >= self.fitness(p2) else p2
        other = p2 if best is p1 else p1
        child = {}
        def insert_or_repair(gene, dest):
            f,sid,t,r = gene
            if any(k[1]==sid for k in dest): return True
            tmp = dest.copy(); tmp[gene] = True
            if self.fitness(tmp) > self.fitness(dest):
                dest[gene] = True; return True
            busy = self.get_busy_map(dest)
            cands = self.find_valid_placements(sid, busy)
            if cands:
                sel = random.choice(cands)
                tmp2 = dest.copy(); tmp2[sel] = True
                if self.fitness(tmp2) >= self.fitness(dest):
                    dest[sel] = True; return True
            return False
        for k in best.keys(): insert_or_repair(k, child)
        for k in other.keys(): insert_or_repair(k, child)
        have = {k[1] for k in child.keys()}
        need = [sid for sid in self.all_sids if sid not in have]
        busy = self.get_busy_map(child)
        for sid in need:
            cands = self.find_valid_placements(sid, busy)
            if cands:
                sel = random.choice(cands)
                child[sel] = True
                busy = self.get_busy_map(child)
        return child

    def mutate(self, individual, k_samples=15):
        if not individual: return individual
        mutated = individual.copy()
        target = random.choice(list(mutated.keys()))
        sid = target[1]
        del mutated[target]
        busy = self.get_busy_map(mutated)
        cands = self.find_valid_placements(sid, busy)
        if not cands:
            mutated[target] = True; return mutated
        sample = random.sample(cands, min(k_samples, len(cands)))
        best, best_f = None, -1e18
        for p in sample:
            tmp = mutated.copy(); tmp[p] = True
            fval = self.fitness(tmp)
            if fval > best_f: best_f, best = fval, p
        mutated[best if best else target] = True
        return mutated

    def run(self):
        if not self.population:
            return {}
        best = max(self.population, key=self.fitness)
        best_f = self.fitness(best)
        patience, stall = 5, 0
        for gen in range(self.generations):
            new_pop = [copy.deepcopy(best)]
            while len(new_pop) < self.population_size:
                p1, p2 = self.select_parents()
                child = self.crossover(p1, p2)
                if random.random() < self.mutation_rate:
                    child = self.mutate(child)
                new_pop.append(child)
            self.population = new_pop
            cur = max(self.population, key=self.fitness)
            cur_f = self.fitness(cur)
            if cur_f > best_f:
                best, best_f, stall = cur, cur_f, 0
                print(f"Generation {gen+1}: New Best Fitness = {best_f:.4f}")
            else:
                stall += 1
            if stall >= patience:
                print(f"Stopping early at generation {gen+1}.")
                break
        print(f"GA Completed: Best Fitness = {best_f:.4f}")
        return best
