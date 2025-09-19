# train_ner.py

import spacy
import random
from spacy.training.example import Example
from training_data import TRAIN_DATA 

def train_custom_ner_model():
    """Creates, trains, and saves a custom spaCy NER model."""
    
    # 1. Create a blank English model
    nlp = spacy.blank("en")
    print("Created blank 'en' model")

    # 2. Add the Named Entity Recognition (NER) pipe to the pipeline
    if "ner" not in nlp.pipe_names:
        ner = nlp.add_pipe("ner", last=True)
    else:
        ner = nlp.get_pipe("ner")

    # 3. Add all unique entity labels to the NER pipe
    #    (spaCy needs to know about them before training)
    for _, annotations in TRAIN_DATA:
        for ent in annotations.get("entities"):
            ner.add_label(ent[2])
    
    # 4. Start the training process
    #    We disable other pipes during training for efficiency
    other_pipes = [pipe for pipe in nlp.pipe_names if pipe != "ner"]
    with nlp.disable_pipes(*other_pipes):
        optimizer = nlp.begin_training()
        
        # Train for 30 iterations (you can adjust this)
        for itn in range(30):
            random.shuffle(TRAIN_DATA)
            losses = {}
            
            for text, annotations in TRAIN_DATA:
                doc = nlp.make_doc(text)
                example = Example.from_dict(doc, annotations)
                nlp.update([example], drop=0.5, sgd=optimizer, losses=losses)
            
            print(f"Iteration {itn+1}/30, Losses: {losses}")

    # 5. Save the trained model to a directory
    output_dir = "./my_custom_ner_model"
    nlp.to_disk(output_dir)
    print(f"\n✅ Model trained and saved to '{output_dir}'")


# --- Main execution block ---
if __name__ == "__main__":
    train_custom_ner_model()