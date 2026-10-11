"""Sauvegarde la base PostgreSQL dans le dossier sauvegardes/ et efface les sauvegardes de plus de 14 jours.

Usage : python manage.py sauvegarder_base   (à lancer chaque jour par une tâche planifiée)
Restaurer : pg_restore --clean -d <base> sauvegardes/<fichier>.dump

pg_dump doit être installé (il est fourni avec PostgreSQL). Sous Windows, indiquer son chemin dans
config/.env : PG_DUMP_PATH=C:\\Program Files\\PostgreSQL\\18\\bin\\pg_dump.exe
Pensez à copier régulièrement le dossier sauvegardes/ ailleurs (clé USB, Google Drive...) :
une sauvegarde sur le même ordinateur ne protège pas d'une panne de disque.
"""
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

JOURS_CONSERVATION = 14


class Command(BaseCommand):
    help = "Sauvegarde la base de données (pg_dump) et supprime les sauvegardes de plus de 14 jours."

    def add_arguments(self, parser):
        parser.add_argument("--dossier", default=str(Path(settings.BASE_DIR) / "sauvegardes"),
                            help="Dossier où ranger les sauvegardes (par défaut : sauvegardes/)")

    def handle(self, *args, **options):
        base = settings.DATABASES["default"]
        dossier = Path(options["dossier"])
        dossier.mkdir(parents=True, exist_ok=True)
        fichier = dossier / f"{base['NAME']}-{datetime.now():%Y-%m-%d_%H%M}.dump"

        commande = [
            os.getenv("PG_DUMP_PATH", "pg_dump"), "--format=custom", f"--file={fichier}",
            f"--host={base['HOST'] or 'localhost'}", f"--port={base['PORT'] or 5432}", f"--username={base['USER']}",
            base["NAME"],
        ]
        # Le mot de passe passe par une variable d'environnement : il n'apparaît jamais dans la liste des processus
        environnement = {**os.environ, "PGPASSWORD": base["PASSWORD"]}
        try:
            subprocess.run(commande, env=environnement, check=True, capture_output=True, text=True)
        except FileNotFoundError:
            raise CommandError("pg_dump est introuvable : indique son chemin dans PG_DUMP_PATH (config/.env).")
        except subprocess.CalledProcessError as erreur:
            fichier.unlink(missing_ok=True)
            raise CommandError(f"La sauvegarde a échoué : {erreur.stderr.strip()}")

        taille = fichier.stat().st_size / 1024
        self.stdout.write(self.style.SUCCESS(f"Sauvegarde créée : {fichier.name} ({taille:.0f} Ko)"))

        limite = datetime.now() - timedelta(days=JOURS_CONSERVATION)
        anciennes = [f for f in dossier.glob("*.dump") if datetime.fromtimestamp(f.stat().st_mtime) < limite]
        for ancienne in anciennes:
            ancienne.unlink()
        if anciennes:
            self.stdout.write(f"{len(anciennes)} sauvegarde(s) de plus de {JOURS_CONSERVATION} jours supprimée(s).")
