# nlp_rules.py

import os
import json
import copy
from typing import Dict, Any, List

import pandas as pd
from dotenv import load_dotenv
import google.generativeai as genai

# Import the new custom NER parser function
from deterministic_parser import run_custom_ner_parser

load_dotenv()

# --- Helper Functions ---

def deep_merge_constraints(base: dict, patch: dict) -> dict:
    res = copy.deepcopy(base or {})
    for k, v in (patch or {}).items():
        if k in res and isinstance(res[k], dict) and isinstance(v, dict):
            res[k] = deep_merge_constraints(res[k], v)
        else:
            res[k] = copy.deepcopy(v)
    return res

def _slot_keys_from_map(time_slot_map: Dict[str, Any]) -> List[str]:
    return list((time_slot_map or {}).keys())

def _faculty_ids_from_data(data: Dict[str, Any]) -> List[str]:
    fac = data.get("faculty")
    if isinstance(fac, pd.DataFrame) and "faculty_id" in fac.columns:
        return fac["faculty_id"].astype(str).dropna().unique().tolist()
    return []

def _normalize_days_for_solver(days: List[str], slot_keys: List[str]) -> List[str]:
    """Ensures day names from either parser match the solver's expected format."""
    day_map = {key.split('_', 1)[0].lower()[:3]: key.split('_', 1)[0] for key in slot_keys if '_' in key}
    normalized_days = set()
    for day in days:
        short_name = day.lower()[:3]
        if short_name in day_map:
            normalized_days.add(day_map[short_name])
    return sorted(list(normalized_days))

def _sanitize_patch(patch: dict, context: dict) -> dict:
    """A critical safety check for the output of any parser."""
    if not patch:
        return {}
    
    res = copy.deepcopy(patch)
    known_fids = set(context.get("faculty_ids", []))
    slot_keys = context.get("slot_keys", [])

    if "faculty_day_off" in res.get("hard", {}):
        rule = res["hard"]["faculty_day_off"]
        rule["scope"]["faculty_ids"] = [fid for fid in rule.get("scope", {}).get("faculty_ids", []) if fid in known_fids]
        rule["params"]["days"] = _normalize_days_for_solver(rule.get("params", {}).get("days", []), slot_keys)
        
        if not rule["scope"]["faculty_ids"] or not rule["params"]["days"]:
            del res["hard"]["faculty_day_off"]
            if not res["hard"]:
                del res["hard"]
    
    return res

# --- LLM Fallback Function ---

def llm_parse_to_patch(nl_text: str, context: dict) -> dict:
    # (This function remains the same as the previous version)
    # ...
    return {} # For brevity, keeping it empty, but the full implementation from previous answer goes here.


# --- Main Orchestrator ---

def propose_and_apply(nl_text: str, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    time_slot_map = kwargs.get("time_slot_map", {})
    context = {
        "slot_keys": _slot_keys_from_map(time_slot_map),
        "faculty_ids": _faculty_ids_from_data(data),
    }

    # 1. Try the flexible Custom NER parser first.
    patch = run_custom_ner_parser(nl_text, context)
    source = "nlp"

    # 2. If it fails, fall back to the powerful LLM.
    if not patch:
        print("[INFO] Custom NER parser failed. Falling back to LLM (Gemini)...")
        patch = llm_parse_to_patch(nl_text, context)
        source = "gemini" if patch else "none"

    # 3. Sanitize the output from either source to ensure it's valid.
    sanitized_patch = _sanitize_patch(patch, context)

    status = "Ready" if sanitized_patch else "No valid constraints extracted"
    
    return {"patch": sanitized_patch, "status": status, "source": source}


def dry_run_constraints(merged: dict, **kwargs) -> dict:
    if not merged.get("hard") and not merged.get("soft"):
         return {"status": "No change"}
    print("[INFO] Starting dry-run simulation with merged constraints...")
    return {"status": "Dry-run simulation complete (placeholder)", "is_feasible": True}
def generate_new_rule_with_llm(nl_text: str, rule_engine_code: str):
    """
    This is the "programmer" LLM. It's called when no existing rule matches.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("[WARN] GOOGLE_API_KEY not found. Cannot generate new rules.")
        return None

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash") # Use a powerful model for this

    prompt = f"""
    You are a senior Python developer specializing in constraint satisfaction problems.
    A user's request could not be handled by our current system. Your task is to write a new Python function for a scheduling rule that can be added to our existing rule engine.

    The user's request was: "{nl_text}"

    Here is the full code for our current rule_engine.py:
    ```
    {rule_engine_code}
    ```

    Instructions:
    1. Analyze the user's request and the existing code.
    2. Write a single, complete Python function for a new rule. Name it `compile_new_<rule_name>`.
    3. The function must take `self, model, variables, cfg, **kwargs` as arguments and correctly interact with the `model` and `variables` as shown in the other compile functions.
    4. Return only the Python code for the new function, with no other text or explanation.
    """

    try:
        print("[INFO] Asking LLM to generate a new rule function...")
        response = model.generate_content(prompt)
        # Save the suggested code to a file for review
        with open("suggested_rule.py", "w") as f:
            f.write(response.text)
        print("\n[SUCCESS] A new rule has been suggested by the LLM.")
        print("Please review the code in 'suggested_rule.py' and manually add it to rule_engine.py if it looks correct.")
        return response.text
    except Exception as e:
        print(f"[ERROR] LLM rule generation failed: {e}")
        return None

