import json

# Charger les données
with open("questions_responses.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Supprimer la dernière question
if data:
    last_key = list(data.keys())[-1]
    print(f"Suppression de la dernière question : {last_key}")
    del data[last_key]

    # Réécrire le fichier sans la dernière question
    with open("questions_responses.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
else:
    print("Le fichier est vide.")
