import pgvector.django.vector
from django.db import migrations


def vider_chunks(apps, schema_editor):
    # Les anciens vecteurs (768, Ollama) sont incompatibles avec la nouvelle taille :
    # on les supprime, il faudra relancer index_documents.py
    apps.get_model("rag", "DocumentChunk").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("rag", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(vider_chunks, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="documentchunk",
            name="embedding",
            field=pgvector.django.vector.VectorField(dimensions=1024),
        ),
    ]
