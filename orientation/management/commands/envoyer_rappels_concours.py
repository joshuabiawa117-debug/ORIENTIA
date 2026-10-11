"""Envoie un email aux élèves abonnés avant chaque date clé d'un concours.

À lancer une fois par jour (tâche planifiée Windows ou cron) :
    python manage.py envoyer_rappels_concours
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from orientation.models import Concours

JOURS_DE_RAPPEL = {7, 3, 1, 0}


class Command(BaseCommand):
    help = "Envoie les rappels de concours (7, 3 et 1 jour(s) avant chaque date clé, puis le jour même)."

    def handle(self, *args, **options):
        aujourdhui = timezone.localdate()
        envoyes = 0
        for concours in Concours.objects.prefetch_related('abonnes').exclude(abonnes=None):
            for libelle, date in [("l'ouverture des inscriptions", concours.date_ouverture),
                                  ("la clôture des inscriptions", concours.date_cloture),
                                  ("les épreuves", concours.date_epreuves)]:
                if not date:
                    continue
                jours = (date - aujourdhui).days
                if jours not in JOURS_DE_RAPPEL:
                    continue
                quand = "aujourd'hui" if jours == 0 else ("demain" if jours == 1 else f"dans {jours} jours")
                for eleve in concours.abonnes.all():
                    if not eleve.email:
                        continue
                    send_mail(
                        subject=f"Rappel OrientIA : {libelle} — {concours.nom} {quand}",
                        message=(
                            f"Bonjour {eleve.first_name or eleve.username},\n\n"
                            f"Petit rappel : {libelle} du « {concours.nom} » a lieu {quand} "
                            f"({date:%d/%m/%Y}).\n\n"
                            + (f"Pièces à fournir :\n" + "\n".join(f"- {p}" for p in concours.liste_pieces()) + "\n\n"
                               if concours.liste_pieces() else "")
                            + (f"Site officiel : {concours.lien_officiel}\n\n" if concours.lien_officiel else "")
                            + "Bon courage !\nL'équipe OrientIA"
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[eleve.email],
                        fail_silently=True,
                    )
                    envoyes += 1
        self.stdout.write(self.style.SUCCESS(f"{envoyes} rappel(s) envoyé(s)."))
