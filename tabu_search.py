# tabu_search.py

import copy
import random
import pandas as pd
from collections import deque, defaultdict

class TabuSearchTimetable:
    def __init__(self, data, next_slot_map,
                 tabu_tenure=10, max_iterations=50,
                 sid_scope=None,
                 sid_to_course=None,
                 allowed_slots_by_sid=None,
                 fixed_assignments=None):  # list[(f,sid,t,r)]
        self.data = data
        self.next_slot_map = next_slot_map
        self.max_iterations = max_iterations
        self.tabu_attrs = deque(maxlen=2000)

        self.sid_scope = set(sid_scope or [])
        self.sid_to_course = dict(sid_to_course or {})
        self.allowed = allowed_slots_by_sid or {}
        self.fixed_assignments = list(fixed_assignments or [])

        self.courses_df = self.data['courses']
        self.data['time_slot_map'] = self.data.get('time_slot_map', {})
        self.time_keys = list(self.data['time_slot_map'].keys())

        base = pd.Series(1, index=self.courses_df.index)
        self.course_details_map = pd.Series(base.values, index=self.courses_df['course_id']).to_dict()

        sc = self.data['student_choices']
        self.course_student_map = sc.groupby('chosen_course_id')['student_id'].apply(list).to_dict()

        self.expert_map = defaultdict(list)
        for _, row in self.data['faculty_expertise'].iterrows():
            self.expert_map[row['course_id']].append(row['faculty_id'])

        self.fixed_busy = self._busy_from_fixed(self.fixed_assignments)

    def _course(self, sid): return self.sid_to_course.get(sid, sid)

    # tabu helpers
    def is_tabu(self, move_attr, best_fitness, candidate_fitness):
        return (move_attr in self.tabu_attrs) and not (candidate_fitness > best_fitness)
    def add_tabu(self, move_attr): self.tabu_attrs.append(move_attr)

    def best_soft_sids(self, solution, top_k=8):
        contrib = []
        base = self.fitness(solution)
        for k in solution:
            tmp = solution.copy(); del tmp[k]
            contrib.append((base - self.fitness(tmp), k))
        contrib.sort(reverse=True, key=lambda x: x[0])
        return [k for _, k in contrib[:min(top_k, len(contrib))]]

    # feasibility + score
    def get_required_slots(self, start_slot, duration): return [start_slot]

    def _busy_from_fixed(self, fixed):
        busy = {'faculty': defaultdict(set), 'room': defaultdict(set), 'student': defaultdict(set)}
        for f, sid, t, r in fixed:
            c = self._course(sid)
            for s in [t]:
                busy['faculty'][f].add(s); busy['room'][r].add(s)
                for stu in self.course_student_map.get(c, []):
                    busy['student'][stu].add(s)
        return busy

    def get_busy_map(self, individual):
        busy = {'faculty': defaultdict(set), 'room': defaultdict(set), 'student': defaultdict(set)}
        for res, d in self.fixed_busy.items():
            for k, v in d.items(): busy[res][k] |= set(v)
        for f, sid, t, r in individual.keys():
            c = self._course(sid)
            s = t
            busy['faculty'][f].add(s); busy['room'][r].add(s)
            for stu in self.course_student_map.get(c, []):
                busy['student'][stu].add(s)
        return busy

    def hard_constraint_violations(self, individual):
        # This function now only checks for faculty and room clashes,
        # matching the logic of the Genetic Algorithm.
        ledger = defaultdict(int)
        
        # 1. Count fixed assignments (faculty and room only)
        for f, sid, t, r in self.fixed_assignments:
            ledger[('f', f, t)] += 1
            ledger[('r', r, t)] += 1
            # The student check that was here has been removed.

        # 2. Count movable assignments (faculty and room only)
        for f, sid, t, r in individual.keys():
            ledger[('f', f, t)] += 1
            ledger[('r', r, t)] += 1
            # The student check that was here has been removed.

        v = 0
        for cnt in ledger.values():
            if cnt > 1:
                v += (cnt - 1)
                
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
        v = self.hard_constraint_violations(individual)
        if v > 0: return -1000.0 * v
        return self.student_gap_score(individual)

    # neighborhoods
    def _room_ok(self, c_id, r_row, group_size):
        rtype = str(r_row.get('room_type', '')).lower()
        cap = int(r_row.get('capacity', 0))
        row = self.courses_df.loc[self.courses_df['course_id'] == c_id]
        ctype = str(row['course_type'].iloc[0]).lower() if len(row) else ''
        is_lab = 'lab' in ctype
        return cap >= group_size and (('lab' in rtype) == is_lab)

    def neighborhood(self, solution):
        neigh = []
        # movable filter
        keys = [k for k in solution.keys() if (not self.sid_scope) or (k[1] in self.sid_scope)]
        if not keys: keys = list(solution.keys())
        ranked = self.best_soft_sids({k: True for k in keys}, top_k=8)
        cand_keys = [k for k in ranked if k in solution] or keys

        rooms_df = self.data['rooms']

        for key_to_move in cand_keys:
            f0, sid0, t0, r0 = key_to_move
            c0 = self._course(sid0)
            tmp = solution.copy(); del tmp[key_to_move]
            base_busy = self.get_busy_map(tmp)
            studs0 = self.course_student_map.get(c0, [])
            group_size0 = len(studs0)

            # 1) Move sid0 within allowed windows
            allowed_t0 = list(self.allowed.get(sid0, self.time_keys))
            for _, r_row in rooms_df.iterrows():
                if not self._room_ok(c0, r_row, group_size0): continue
                r_id = r_row['room_id']
                for t_new in allowed_t0:
                    if t_new == t0: continue
                    if (t_new in base_busy['room'].get(r_id, set())) or (t_new in base_busy['faculty'].get(f0, set())):
                            continue

                    n = tmp.copy(); n[(f0, sid0, t_new, r_id)] = True
                    neigh.append(('move', ('sid', sid0, 't', t_new), n))

            # 2) Swap times with another movable sid (keep rooms/faculties)
            for other in keys:
                if other == key_to_move:
                    continue
                f1, sid1, t1, r1 = other
                c1 = self._course(sid1)
                # allowed windows check
                if (t1 not in self.allowed.get(sid0, self.time_keys)) or (t0 not in self.allowed.get(sid1, self.time_keys)):
                    continue
                # room suitability
                r0_row = rooms_df.loc[rooms_df['room_id'] == r0]
                r1_row = rooms_df.loc[rooms_df['room_id'] == r1]
                if r0_row.empty or r1_row.empty:
                    continue
                if not (self._room_ok(c0, r1_row.iloc[0], group_size0) and
                        self._room_ok(c1, r0_row.iloc[0], len(self.course_student_map.get(c1, [])))):
                    continue

                # Start from solution with BOTH keys removed
                n = solution.copy()
                if key_to_move in n:
                    del n[key_to_move]
                if other in n:
                    del n[other]

                # Busy after removing both
                base2 = self.get_busy_map(n)

                # place sid0@t1,r1 with f0
                if (t1 in base2['room'].get(r1, set())) or (t1 in base2['faculty'].get(f0, set())):
                    continue
                n[(f0, sid0, t1, r1)] = True

                # Busy after inserting first
                busy2 = self.get_busy_map(n)

                # place sid1@t0,r0 with f1
                if (t0 in busy2['room'].get(r0, set())) or (t0 in busy2['faculty'].get(f1, set())):
                    # rollback first insertion to avoid accumulating partials
                    del n[(f0, sid0, t1, r1)]
                    continue

                n[(f1, sid1, t0, r0)] = True
                neigh.append(('swap', ('sid0', sid0, 't1', t1, 'sid1', sid1, 't0', t0), n))

        return neigh

    def run(self, initial_solution):
        current = copy.deepcopy(initial_solution)
        best = current; best_fit = self.fitness(best)
        for it in range(self.max_iterations):
            cand = self.neighborhood(current)
            if not cand: break
            scored = []
            for move_type, attr, sol in cand:
                f = self.fitness(sol)
                if not self.is_tabu(attr, best_fit, f):
                    scored.append((f, move_type, attr, sol))
            if not scored: break
            scored.sort(key=lambda x: x[0], reverse=True)
            f, move_type, attr, sel = scored[0]
            current = sel
            self.add_tabu(attr)
            if f > best_fit:
                best, best_fit = sel, f
            if (it + 1) % 10 == 0:
                print(f"Tabu Iter {it+1}: Best={best_fit:.4f}")
        return best