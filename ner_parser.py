# In ner_parser.py
import spacy

class NerParser:
    def __init__(self, model_path="./my_custom_ner_model"):
        """Loads the custom-trained spaCy NER model from disk."""
        try:
            self.nlp = spacy.load(model_path)
            print("[NER Parser] Custom NER model loaded successfully.")
        except IOError:
            print(f"[Error] Could not load NER model from {model_path}. Please run train_ner.py first.")
            self.nlp = None

    def extract_entities(self, nl_text: str) -> dict:
        """Extracts all named entities from a text and returns them as a dict."""
        if not self.nlp:
            return {}
        
        # --- FIX: Add this sanitization step ---
        # Replace non-breaking spaces with regular spaces
        clean_text = nl_text.replace('\u00A0', ' ')
        
        # Process the cleaned text instead of the original
        doc = self.nlp(clean_text)
        entities = {ent.label_: ent.text for ent in doc.ents}
        return entities