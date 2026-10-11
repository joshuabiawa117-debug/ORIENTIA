"""Poser une question à OrientIA depuis le terminal : python poser_question.py"""
import os

import django

# Configurer Django pour utiliser les modèles en dehors du serveur
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from rag.assistant import generer_reponse, rechercher_chunks_pertinents, sources_de  # noqa: E402

if __name__ == "__main__":
    question = input("Pose ta question d'orientation : ")

    chunks = rechercher_chunks_pertinents(question)
    print(f"\n{len(chunks)} passage(s) pertinent(s) trouvé(s) dans : {', '.join(sources_de(chunks))}\n")

    print("=== Réponse ===")
    print(generer_reponse(question, chunks))
