import spacy

# Load your newly trained custom model from the directory
nlp_custom = spacy.load("./my_custom_ner_model")

# Test with a new sentence that was NOT in your training data
test_sentence = "Can you make sure ROOM101 is reserved for professor FAC007?"

print(f"Testing sentence: '{test_sentence}'")
doc = nlp_custom(test_sentence)

print("\nEntities found:")
for ent in doc.ents:
    print(f"- Text: '{ent.text}', Label: '{ent.label_}'")