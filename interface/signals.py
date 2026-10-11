from allauth.account.signals import user_signed_up
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Profil


@receiver(post_save, sender=User)
def creer_profil(sender, instance, created, **kwargs):
    """Chaque nouvel utilisateur (formulaire ou Google) reçoit un profil vide à compléter."""
    if created:
        Profil.objects.get_or_create(utilisateur=instance)


@receiver(user_signed_up)
def noter_consentement_google(sender, request, user, **kwargs):
    """Inscription par Google : le bouton indique qu'on accepte les conditions et la politique de confidentialité."""
    Profil.objects.filter(utilisateur=user, date_consentement__isnull=True).update(date_consentement=timezone.now())
