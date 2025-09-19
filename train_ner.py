import spacy
import random
from spacy.training import Example

# Import your training data
from training_data import TRAIN_DATA

def train_custom_ner(iterations=20):
    """
    Trains a custom NER model using the provided training data.
    """
    # 1. Start with a blank English model.
    # A blank model is better than a pre-trained one when your entities are very custom.
    nlp = spacy.blank("en")
    print("Created blank 'en' model")

    # 2. Add the NER pipeline component.
    if "ner" not in nlp.pipe_names:
        ner = nlp.add_pipe("ner", last=True)
    else:
        ner = nlp.get_pipe("ner")

    # 3. Add your custom entity labels to the NER pipeline.
    # This tells the model what labels it needs to learn.
    for _, annotations in TRAIN_DATA:
        for ent in annotations.get("entities"):
            ner.add_label(ent[2])

    # 4. Start the training process.
    # We disable other pipelines because we only want to train the NER component.
    other_pipes = [pipe for pipe in nlp.pipe_names if pipe != "ner"]
    with nlp.disable_pipes(*other_pipes):
        optimizer = nlp.begin_training()
        print("Training the model...")

        for itn in range(iterations):
            random.shuffle(TRAIN_DATA)
            losses = {}
            
            for text, annotations in TRAIN_DATA:
                # Create an Example object for each training instance
                doc = nlp.make_doc(text)
                example = Example.from_dict(doc, annotations)
                # Update the model with the example
                nlp.update([example], drop=0.5, losses=losses, sgd=optimizer)
            
            print(f"Iteration {itn + 1}/{iterations} - Losses: {losses}")

    # 5. Save the trained model to a directory.
    # This model can now be loaded and used in your main application.
    output_dir = "./custom_ner_model"
    nlp.to_disk(output_dir)
    print(f"Saved trained model to '{output_dir}'")


if __name__ == "__main__":
    train_custom_ner()
