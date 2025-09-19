import pandas as pd
from collections import defaultdict

# Local module imports
from preprocessor import run_preprocessing_pipeline
from sat_solver import BatchTimetableSATModel
from time_slots import generate_time_slots
from ga_solver import GeneticAlgorithmTimetable
from tabu_search import TabuSearchTimetable
from scorer import soft_penalty

def run_memetic_optimization(feasible_schedule, data, time_slot_map, next_slot_map, soft_cfg):
    """
    Takes a feasible schedule from the SAT solver and uses GA and Tabu Search
    to "polish" it, focusing on soft objectives like student compactness.
    """
    print("\n--- Phase 2 & 3: Memetic Polishing ---")

    sid_to_course = {}
    sid_to_batch_or_group = {}
    current_assignments_by_sid = []
    
    core_counters = defaultdict(int)
    for (f, c, t, r, b) in feasible_schedule:
        core_counters[(b, c)] += 1
        k = core_counters[(b, c)]
        sid = f"CORE::{b}::{c}::{k}"
        sid_to_course[sid] = c
        sid_to_batch_or_group[sid] = b
        current_assignments_by_sid.append((f, sid, t, r))

    print(f"[Memetic] Converted SAT schedule to {len(current_assignments_by_sid)} session assignments.")

    movable_sids = set(sid_to_course.keys())
    fixed_assignments = []
    seed_schedule = {(f, sid, t, r): True for (f, sid, t, r) in current_assignments_by_sid}

    if not movable_sids:
        print("[Memetic] No movable sids found. Skipping polishing.")
        return feasible_schedule

    print("\n[Memetic] Running Genetic Algorithm for initial optimization...")
    ga = GeneticAlgorithmTimetable(
        data=data,
        time_slot_map=time_slot_map,
        next_slot_map=next_slot_map,
        population_size=24,
        generations=15,
        mutation_rate=0.4,
        crossover_rate=0.8,
        sid_scope=movable_sids,
        sid_to_course=sid_to_course,
        fixed_assignments=fixed_assignments,
        seed_schedule=seed_schedule
    )
    
    initial_population = [seed_schedule]
    for _ in range(ga.population_size - 1):
        mutated_seed = ga.mutate(seed_schedule)
        initial_population.append(mutated_seed)
    
    ga.initialize_population(initial_population)
    ga_solution = ga.run()

    print("\n[Memetic] Running Tabu Search for final polishing...")
    tabu = TabuSearchTimetable(
        data=data,
        time_slot_map=time_slot_map,
        next_slot_map=next_slot_map,
        tabu_tenure=15,
        max_iterations=75,
        sid_scope=movable_sids,
        sid_to_course=sid_to_course,
        fixed_assignments=fixed_assignments,
        soft_config=soft_cfg 
    )
    final_polished_schedule_dict = tabu.run(ga_solution)
    
    final_schedule_list = []
    polished_assignments = set(final_polished_schedule_dict.keys())
    for (f, sid, t, r) in polished_assignments:
        course_id = sid_to_course[sid]
        batch_or_group = sid_to_batch_or_group[sid]
        final_schedule_list.append((f, course_id, t, r, batch_or_group))
        
    return final_schedule_list

def run_timetabling_pipeline(time_limit=300):
    """
    Orchestrates the end-to-end, three-phase timetabling process.
    """
    time_slots, time_slot_map, next_slot_map = generate_time_slots()
    data, core_batches, core_batch_sessions = run_preprocessing_pipeline()
    
    core_solver = BatchTimetableSATModel(
        data=data,
        batches=core_batches,
        batch_sessions=core_batch_sessions,
        time_slot_map=time_slot_map,
        next_slot_map=next_slot_map,
    )
    
    feasible_schedule, _, ok = core_solver.solve(time_limit=time_limit)
    
    if not ok:
        print("\n❌ CRITICAL ERROR: The SAT solver could not produce a feasible schedule.")
        return [], {}

    soft_cfg = core_solver.soft_config 
    final_schedule_list = run_memetic_optimization(
        feasible_schedule, data, time_slot_map, next_slot_map, soft_cfg
    )
    
    return final_schedule_list, core_batches
