"""Quiz d'entraînement aux concours, générés par OrientIA (Groq)."""
import json

from rag.ia import generer_json

MATIERES_QUIZ = [
    "Mathématiques", "Physique", "Chimie", "Biologie", "Culture générale",
    "Français", "Anglais", "Informatique", "Économie",
]
NOMBRE_QUESTIONS = 5


def valider(questions):
    """Ne garde que les questions bien formées : 4 choix, une bonne réponse, une explication."""
    propres = []
    for q in questions:
        try:
            choix = [str(c).strip() for c in q["choix"]]
            reponse = int(q["reponse"])
            if q["question"].strip() and len(choix) == 4 and all(choix) and 0 <= reponse < 4:
                propres.append({
                    "question": q["question"].strip(),
                    "choix": choix,
                    "reponse": reponse,
                    "explication": str(q.get("explication", "")).strip(),
                })
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return propres


def creer_quiz(matiere, concours=None, langue="fr"):
    """Renvoie une liste de questions à choix multiples (lève une exception si OrientIA échoue)."""
    cible = f"le « {concours} »" if concours else "les concours d'entrée des grandes écoles camerounaises"
    prompt = f"""Tu es OrientIA, un assistant qui aide les bacheliers camerounais à préparer {cible}.
Crée {NOMBRE_QUESTIONS} questions à choix multiples de {matiere}, niveau Terminale / concours post-bac,
variées et de difficulté progressive, avec exactement 4 choix chacune dont une seule correcte.
Pour chaque question, ajoute une explication courte (1 à 2 phrases) de la bonne réponse.

{"IMPORTANT : rédige les questions, les choix et les explications en ANGLAIS (l'élève est anglophone)." if langue == "en" else ""}
Réponds UNIQUEMENT avec un objet JSON de cette forme :
{{"questions": [{{"question": "...", "choix": ["...", "...", "...", "..."], "reponse": 0, "explication": "..."}}]}}
où "reponse" est l'indice (0 à 3) du bon choix."""

    donnees = json.loads(generer_json(prompt))
    # Le modèle renvoie normalement {"questions": [...]}, mais parfois directement la liste
    if isinstance(donnees, dict):
        donnees = donnees.get("questions") or next((v for v in donnees.values() if isinstance(v, list)), [])
    questions = valider(donnees if isinstance(donnees, list) else [])
    if not questions:
        raise ValueError("Aucune question valide dans la réponse d'OrientIA")
    return questions[:NOMBRE_QUESTIONS]
