"""Supprime les données qui n'ont plus à être gardées (engagements de la politique de confidentialité).

Usage : python manage.py nettoyer_donnees   (à lancer chaque jour par une tâche planifiée)
"""
from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from rag.models import EchangeChat

JOURS_CONVERSATIONS_VISITEURS = 30


class Command(BaseCommand):
    help = "Supprime les conversations des visiteurs sans compte de plus de 30 jours et les sessions expirées."

    def handle(self, *args, **options):
        limite = timezone.now() - timedelta(days=JOURS_CONVERSATIONS_VISITEURS)
        nb, _detail = EchangeChat.objects.filter(utilisateur=None, date__lt=limite).delete()
        call_command("clearsessions")
        self.stdout.write(self.style.SUCCESS(f"{nb} échange(s) de visiteurs supprimé(s), sessions expirées effacées."))
