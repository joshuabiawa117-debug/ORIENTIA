"""Indexe les PDF du dossier documents/ pour qu'OrientIA puisse y chercher ses réponses.

Usage : python manage.py indexer_documents
À relancer après avoir ajouté ou remplacé un PDF dans documents/.
"""
from pathlib import Path

from django.conf import settings
from django.contrib.postgres.search import SearchVector
from django.core.management.base import BaseCommand
from django.db import transaction
from pypdf import PdfReader

from rag.assistant import CONFIG_RECHERCHE
from rag.decoupage import decouper
from rag.models import DocumentChunk


def extraire_texte_pdf(chemin):
    """Extrait tout le texte d'un fichier PDF."""
    return "\n".join((page.extract_text() or "") for page in PdfReader(chemin).pages)


class Command(BaseCommand):
    help = "Découpe les PDF de documents/ en passages et construit l'index de recherche d'OrientIA."

    def handle(self, *args, **options):
        dossier = Path(settings.BASE_DIR) / "documents"
        fichiers = sorted(f for f in dossier.iterdir() if f.suffix.lower() == ".pdf")
        self.stdout.write(f"{len(fichiers)} fichier(s) PDF trouvé(s).")

        passages = []
        for fichier in fichiers:
            morceaux = decouper(extraire_texte_pdf(fichier))
            passages += [DocumentChunk(source=fichier.name, contenu=m) for m in morceaux]
            self.stdout.write(f"  {fichier.name} : {len(morceaux)} passage(s)")

        # Tout ou rien : si une erreur survient, l'ancien index reste en place
        with transaction.atomic():
            DocumentChunk.objects.all().delete()
            DocumentChunk.objects.bulk_create(passages)
            # Index plein texte en français, insensible aux accents : tout se fait dans PostgreSQL, sans API
            DocumentChunk.objects.update(recherche=SearchVector("contenu", config=CONFIG_RECHERCHE))

        self.stdout.write(self.style.SUCCESS(f"Indexation terminée : {len(passages)} passages consultables par OrientIA."))
