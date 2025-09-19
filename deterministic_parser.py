# deterministic_parser.py

import spacy
from typing import Dict, Any, Optional

# --- Load Your Custom-Trained NER Model ---
# This is the most important line. It tells spaCy to load the model
# you just trained from the 'custom_ner_model' directory.
try:
    NLP = spacy.load("./custom_ner_model")
    print("Loaded custom NER model.")
except IOError:
    print("\n[ERROR] Custom NER model not found.")
    print("Please run 'python train_ner.py' to train and save the model first.\n")
    # This fallback prevents the app from crashing if the model hasn't been trained yet.
    NLP = spacy.blank("en")


# --- Rule Assembler ---

def assemble_rule_from_entities(doc: spacy.tokens.Doc, context: dict) -> Optional[dict]:
    """
    Assembles a JSON rule from the entities predicted by your custom model.
    """
    entities = {
        "FACULTY_ID": [],
        "DAY": [],
        "INTENT": []
    }
    # The doc.ents now contain entities predicted by YOUR model.
    for ent in doc.ents:
        if ent.label_ in entities:
            entities[ent.label_].append(ent.text)

    # If the model found all the necessary pieces...
    if entities["FACULTY_ID"] and entities["DAY"] and entities["INTENT"]:
        known_fids = set(context.get("faculty_ids", []))
        # ...and the faculty ID is a valid one...
        valid_fids = [fid for fid in entities["FACULTY_ID"] if fid in known_fids]
        
        if valid_fids:
            # ...then build the rule.
            return {
                "hard": {
                    "faculty_day_off": {
                        "enabled": True,
                        "scope": {"faculty_ids": valid_fids},
                        # The days will be normalized later to match your solver's format.
                        "params": {"days": entities["DAY"]},
                    }
                }
            }
    return None


# --- Main Parser Function ---

def run_custom_ner_parser(nl_text: str, context: dict) -> Optional[dict]:
    """
    The main entry point that uses your custom NER model to parse text.
    """
    # Use your custom NLP model to process the text.
    doc = NLP(nl_text)
    # Assemble the rule based on the predicted entities.
    return assemble_rule_from_entities(doc, context)
