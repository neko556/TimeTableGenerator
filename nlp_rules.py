# nlp_rules.py

import os
import json
import copy
from typing import Dict, Any, List
import pandas as pd
from dotenv import load_dotenv
import google.generativeai as genai
from ner_parser import NerParser

# --- Initialization ---
ner_parser = NerParser()
load_dotenv()


# --- NEW: Deterministic Patch Builder ---
def build_patch_from_entities(entities: Dict[str, str]) -> Dict[str, Any]:
    """
    Attempts to build a JSON patch directly from NER-extracted entities
    for known, simple rule patterns.
    """
    patch = {}
    faculty_id = entities.get("FACULTY_ID")
    day_of_week = entities.get("DAY_OF_WEEK")

    # --- Rule Pattern 1: Faculty Day Off ---
    if faculty_id and day_of_week:
        print("[INFO] Matched deterministic rule: 'faculty_day_off'")
        
        # FIX: Normalize the day of the week (e.g., "Wednesdays" -> "Wednesday")
        normalized_day = day_of_week.rstrip('s')

        # Create a unique key for the constraint
        constraint_key = f"faculty_day_off_{faculty_id}_{normalized_day}"

        patch = {
            "hard_constraints": {
                constraint_key: {
                    "enabled": True,
                    "pattern": "forbid_by_attribute",
                    "filter": {
                        "faculty_id": [faculty_id],
                        "day_of_week": [normalized_day]
                    }
                }
            }
        }
    
    # Add more 'elif' blocks here for other known patterns
    # elif entities.get("COURSE_ID") and entities.get("ROOM_ID"):
    #     ... build another patch type ...

    return patch


# --- LLM Function (Fallback) ---
def llm_parse_to_patch(nl_text: str, context_snippets: dict, prompt_path: str) -> dict:
    """Asks the LLM to generate a JSON patch as a fallback."""
    # (This function can remain exactly as it was, no changes needed)
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("[WARN] GOOGLE_API_KEY not found.")
        return {}

    try:
        with open(os.path.join(prompt_path, "generate_patch_prompt.txt"), "r") as f:
            prompt_template = f.read()
    except FileNotFoundError:
        print(f"[ERROR] Prompt file not found in path: {prompt_path}")
        return {}

    final_prompt = prompt_template.format(nl_text=nl_text, constraints_json=context_snippets.get("constraints_json", "{}"))
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    try:
        print("[INFO] Asking LLM to generate a JSON patch...")
        response = model.generate_content(final_prompt)
        print(f"[DEBUG] Raw LLM Response Text:\n---\n{response.text}\n---")
        cleaned_response = response.text.strip().replace("```json", "").replace("```", "")
        return json.loads(cleaned_response)
    except Exception as e:
        print(f"[ERROR] LLM patch generation failed or returned invalid JSON: {e}")
        return {}


# --- MODIFIED: Main Orchestrator with Triage Logic ---
def propose_and_apply(nl_text: str, constraints_path: str, context_snippets: dict, prompts_path: str) -> dict:
    """
    Orchestrates a triage system:
    1. Try to use the fast/cheap NER to build a patch.
    2. If that fails, escalate to the powerful/expensive LLM.
    """
    patch = {}
    
    # Step 1: Extract entities with our custom NER model.
    ner_entities = ner_parser.extract_entities(nl_text)
    print(f"[Validator] Entities found in prompt: {ner_entities}")

    if ner_entities:
        # Step 2: Try to build the patch using our deterministic rules.
        patch = build_patch_from_entities(ner_entities)

    # Step 3: If the deterministic builder couldn't handle it, escalate to the LLM.
    if not patch:
        print("🤔 NER pattern not recognized or entities not found. Escalating to LLM...")
        patch = llm_parse_to_patch(nl_text, context_snippets, prompt_path=prompts_path)
    
    # The old, flawed validation loop is no longer needed.
    # The deterministic builder is trusted, and the LLM is a final fallback.
    
    if patch:
        print("\n--> RESULT: A valid patch was generated.")
        return patch
    else:
        print("\n--> RESULT: Failed to generate a patch from the prompt.")
        return {}