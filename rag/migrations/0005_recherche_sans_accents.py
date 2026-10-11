"""Recherche insensible aux accents : « ecole » trouve « école », « ingenieur » trouve « ingénieur ».

Crée l'extension PostgreSQL « unaccent » et une configuration de recherche « french_unaccent »
(accents retirés, puis racines françaises), puis recalcule l'index des passages déjà enregistrés.
"""
from django.contrib.postgres.operations import UnaccentExtension
from django.contrib.postgres.search import SearchVector
from django.db import migrations

CREER_CONFIG = """
CREATE TEXT SEARCH CONFIGURATION french_unaccent (COPY = french);
ALTER TEXT SEARCH CONFIGURATION french_unaccent
    ALTER MAPPING FOR hword, hword_part, word WITH unaccent, french_stem;
"""
SUPPRIMER_CONFIG = "DROP TEXT SEARCH CONFIGURATION IF EXISTS french_unaccent;"


def reindexer(apps, schema_editor, config):
    DocumentChunk = apps.get_model('rag', 'DocumentChunk')
    DocumentChunk.objects.update(recherche=SearchVector('contenu', config=config))


class Migration(migrations.Migration):

    dependencies = [
        ('rag', '0004_echangechat'),
    ]

    operations = [
        UnaccentExtension(),
        migrations.RunSQL(CREER_CONFIG, SUPPRIMER_CONFIG),
        migrations.RunPython(
            lambda apps, editor: reindexer(apps, editor, 'french_unaccent'),
            lambda apps, editor: reindexer(apps, editor, 'french'),
        ),
    ]
