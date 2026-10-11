"""Convertit une base existante : le point PostGIS « localisation » devient latitude + longitude.

Sur une nouvelle base, la colonne « localisation » n'existe pas (voir 0001) : la migration ne fait rien.
Le modèle Django, lui, a déjà latitude et longitude depuis 0001 : seule la base de données change ici.
"""
from django.db import migrations

CONVERTIR = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'etablissements_etablissement' AND column_name = 'localisation'
    ) THEN
        ALTER TABLE etablissements_etablissement
            ADD COLUMN latitude double precision, ADD COLUMN longitude double precision;
        UPDATE etablissements_etablissement SET latitude = ST_Y(localisation), longitude = ST_X(localisation);
        ALTER TABLE etablissements_etablissement
            ALTER COLUMN latitude SET NOT NULL, ALTER COLUMN longitude SET NOT NULL;
        ALTER TABLE etablissements_etablissement DROP COLUMN localisation;
    END IF;
END
$$;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('etablissements', '0004_region_position_source'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(CONVERTIR, migrations.RunSQL.noop)],
        ),
    ]
