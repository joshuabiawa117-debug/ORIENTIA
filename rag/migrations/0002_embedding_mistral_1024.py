from django.db import migrations


class Migration(migrations.Migration):
    """Ancienne migration (taille des vecteurs pgvector), devenue vide : voir l'explication dans 0001."""

    dependencies = [
        ("rag", "0001_initial"),
    ]

    operations = []
