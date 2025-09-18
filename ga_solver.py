
import random
import copy
from collections import defaultdict
import pandas as pd
import time

import math 


class GeneticAlgorithmTimetable:
    """
    Session-level GA (sid_scope) with fixed occupancy and faculty/room-only feasibility.
    - No student no-overlap in feasibility (mirrors elective CP-SAT model).
    - Soft objective = student compactness (student_gap_score).
    - Seed-aware repair builds a feasible first individual to avoid negative wall scores.
    """

    def __init__(self, data, next_slot_map,
                 population_size=24, generations=10,
                 mutation_rate=0.35, crossover_rate=0.8,
                 sid_scope=None,
                 sid_to_course=None,
                 fixed_assignments=None,            
                 allowed_slots_by_sid=None,   
                             
                 seed_schedule=None,
                 soft_config=None):               
        self.data = data
        self.next_slot_map = next_slot_map
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.soft_cfg = dict(soft_config or {})
        self.population = []

        self.sid_scope = list(sid_scope or [])
        self.sid_to_course = dict(sid_to_course or {})
        self.fixed_assignments = list(fixed_assignments or [])
        self.allowed_slots_by_sid = allowed_slots_by_sid or {}
        self.seed_schedule = dict(seed_schedule or {})

        print("\n--- Pre-computing GA data for optimization ---")
        t0 = time.time()
        self.courses_df = self.data['courses']
        # clamp durations to 1 slot for post-optimization
        base = pd.Series(1, index=self.courses_df.index)
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

        # ensure seed time is in domain for each sid
        for (f, sid, t, r) in self.seed_schedule.keys():
            self.allowed_slots_by_sid.setdefault(sid, set()).add(t)

        self.sid_candidate_pool = {}
        print(f"Pre-computation completed in {time.time()-t0:.2f} seconds.")

    # --------- helpers ---------
    def _course(self, sid):  # sid -> course_id
        return self.sid_to_course.get(sid, sid)

    def _busy_from_fixed(self, fixed):
        # faculty/room occupancy only
        busy = {'faculty': defaultdict(set), 'room': defaultdict(set)}
        for f, sid, t, r in fixed:
            busy['faculty'][f].add(t)
            busy['room'][r].add(t)
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

    # --------- feasibility (faculty/room only) ---------
    def get_busy_map(self, individual):
        busy = {'faculty': defaultdict(set), 'room': defaultdict(set)}
        # merge fixed
        for res, d in self.fixed_busy_map.items():
            for k, v in d.items():
                busy[res][k] |= set(v)
        # add variable
        for (f, sid, t, r) in individual.keys():
            busy['faculty'][f].add(t)
            busy['room'][r].add(t)
        return busy

    def update_busy_map(self, busy_map, assignment):
        f, sid, t, r = assignment
        busy_map['faculty'][f].add(t)
        busy_map['room'][r].add(t)

    def is_placement_valid(self, f_id, r_id, students_unused, slots, busy_map):
        s = slots[0]  # 1-slot moves
        if s in busy_map['faculty'].get(f_id, set()):
            return False
        if s in busy_map['room'].get(r_id, set()):
            return False
        # no student check (electives allow overlaps)
        return True

    def find_valid_placements(self, sid, busy_map):
        vs = []
        c = self._course(sid)
        for (f_id, _, t_slot, r_id) in self.sid_candidate_pool.get(sid, []):
            if self.is_placement_valid(f_id, r_id, None, [t_slot], busy_map):
                vs.append((f_id, sid, t_slot, r_id))
        return vs
    def initialize_population(self, initial_schedules):
            """
            Create the initial GA population.
            - initial_schedules: list with at least one dict {(f,sid,t,r): True} used as seed.
            - If sid_scope was not provided, infer it from the seed.
            - Build candidate pools once the scope is known.
            - First individual is a repaired/feasible version of the seed; the rest are randomized feasible builds.
            """
            print("Initializing a diverse and valid GA population...")
            seed = initial_schedules[0] if initial_schedules else {}
            if not self.all_sids:
                self.all_sids = sorted({k[1] for k in seed.keys()})
            if not self.all_sids:
                self.population = [seed]
                print("GA: Empty scope.")
                return

            # Build candidate pool after scope is known
            self.sid_candidate_pool = self._precompute_candidate_pool()

            # Seeded, repaired individual
            repaired = self.create_valid_individual(seed)
            self.population = [repaired]

            # Fill the rest with randomized feasible individuals
            while len(self.population) < self.population_size:
                self.population.append(self.create_valid_individual({}))

            print(f"GA population initialized with {len(self.population)} individuals.")


    # --------- build individual (with seed-aware repair) ---------
    def create_valid_individual(self, initial_assignments):
        """
        Build a feasible individual:
        - start from fixed-only busy map,
        - keep seed assignments if feasible vs fixed,
        - then greedily place remaining sids,
        - fallback: add seed slot into domain and rebuild candidates for a sid if empty,
        - final safety: if still empty, place one feasible candidate.
        """
        individual = {}
        busy_map = self.get_busy_map({})  # merges fixed only
        seen_sids = set()

        # 1) keep feasible seed genes
        for (f, sid, t, r) in initial_assignments.keys():
            if sid not in set(self.all_sids):
                continue
            if sid in seen_sids:
                continue
            if self.is_placement_valid(f, r, None, [t], busy_map):
                individual[(f, sid, t, r)] = True
                self.update_busy_map(busy_map, (f, sid, t, r))
                seen_sids.add(sid)

        # 2) place remaining sids
        to_place = [sid for sid in self.all_sids if sid not in seen_sids]
        random.shuffle(to_place)
        rooms_df = self.data['rooms']
        for sid in to_place:
            cands = self.find_valid_placements(sid, busy_map)
            if not cands:
                # fallback: add seed time and rebuild pool for this sid
                for (f0, sid0, t0, r0) in initial_assignments.keys():
                    if sid0 == sid:
                        self.allowed_slots_by_sid.setdefault(sid, set()).add(t0)
                        # rebuild candidates JUST for this sid
                        self.sid_candidate_pool[sid] = []
                        c = self._course(sid)
                        n = len(self.course_student_map.get(c, []))
                        row = self.courses_df.loc[self.courses_df['course_id'] == c]
                        ctype = str(row['course_type'].iloc[0]).lower() if len(row) else ''
                        is_lab = 'lab' in ctype
                        for _, r in rooms_df.iterrows():
                            rtype = str(r.get('room_type', '')).lower()
                            cap = int(r.get('capacity', 0))
                            if cap >= n and (('lab' in rtype) == is_lab):
                                for f_id in self.expert_map.get(c, []):
                                    for t_slot in list(self.allowed_slots_by_sid.get(sid, self.time_keys)):
                                        self.sid_candidate_pool[sid].append((f_id, sid, t_slot, r['room_id']))
                        cands = self.find_valid_placements(sid, busy_map)
                        break

            if cands:
                pick = random.choice(cands)
                individual[pick] = True
                self.update_busy_map(busy_map, pick)

        # 3) final safety: ensure non-empty individual
        if not individual and self.all_sids:
            first_sid = self.all_sids[0]
            busy_map2 = self.get_busy_map({})
            cands2 = self.find_valid_placements(first_sid, busy_map2)
            if cands2:
                pick = random.choice(cands2)
                individual[pick] = True
        return individual


    # --------- objective ---------
    def hard_constraint_violations(self, individual):
        # count faculty/room collisions only
        ledger = defaultdict(int)
        for f, sid, t, r in self.fixed_assignments:
            ledger[('f', f, t)] += 1
            ledger[('r', r, t)] += 1
        for f, sid, t, r in individual.keys():
            ledger[('f', f, t)] += 1
            ledger[('r', r, t)] += 1
        v = 0
        for cnt in ledger.values():
            if cnt > 1:
                v += (cnt - 1)
        return v

    def student_gap_score(self, individual):
        # soft compactness: no crash for empty or day-less schedules
        if not individual:
            return 0.0
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
                if not hours:
                    continue
                days += 1
                if len(hours) > 1:
                    hours.sort()
                    gaps += (hours[-1] - hours[0] + 1) - len(hours)
        if days <= 0:
            return 0.0
        avg_gap = gaps / days
        return 1.0 / (1.0 + avg_gap)
    def fitness(self, individual):
        # Keep existing hard feasibility check
        v = self.hard_constraint_violations(individual)
        if v > 0:
            return -1e9 * float(v)  # strong penalty for infeasible
        # Align with CP-SAT soft objective (minimize penalty => maximize -penalty)
        pen = soft_penalty(individual, self.soft_cfg, self.next_slot_map)
        if not math.isfinite(pen):
            return -1e9
        return -float(pen)
    # --------- operators ---------
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

    # --------- loop ---------
    def run(self):
        if not self.population:
            return {}
        import math

        def safe_fit(ind):
            f = self.fitness(ind)
            return (-1e12 if (f is None or not math.isfinite(f)) else float(f))

        def safe_max(pop):
            # returns (best_individual, best_fitness_float) with finite fitness
            scored = [(safe_fit(ind), ind) for ind in pop]
            if not scored:
                return {}, -1e12
            scored.sort(key=lambda x: x[0], reverse=True)
            return scored[0][1], scored[0][0]

        # Seed best
        best, best_f = safe_max(self.population)
        patience, stall = 5, 0

        for gen in range(self.generations):
            new_pop = [copy.deepcopy(best)]
            while len(new_pop) < self.population_size:
                # Parent selection should also use safe fitness
                p1, p2 = self.select_parents()
                # Repair if parents are empty
                if not p1 or not isinstance(p1, dict):
                    p1 = best
                if not p2 or not isinstance(p2, dict):
                    p2 = best
                child = self.crossover(p1, p2)
                if random.random() < self.mutation_rate:
                    child = self.mutate(child)
                new_pop.append(child)

            # Keep only valid, finite-fitness individuals
            self.population = [
                ind for ind in new_pop
                if safe_fit(ind) > -1e12
            ]
            if not self.population:
                # fallback to best
                self.population = [copy.deepcopy(best)]

            cur, cur_f = safe_max(self.population)
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
