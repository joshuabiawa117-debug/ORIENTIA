"""Règles de sécurité de la messagerie privée et masquage automatique des contenus signalés."""
from django.db.models import Q
from django.utils.translation import gettext as _

from .models import SEUIL_MASQUAGE, Blocage


def profil_ou_none(user):
    return getattr(user, 'profil', None)


def raison_refus_message(expediteur, destinataire):
    """Renvoie None si expediteur peut écrire en privé à destinataire, sinon la raison à afficher.

    - Un blocage, dans un sens ou dans l'autre, empêche tout message.
    - Pour protéger les mineurs, un adulte et un mineur ne peuvent s'écrire que si l'adulte
      a un badge vérifié (contributeur, ambassadeur, conseiller) attribué par l'équipe.
    - Âge inconnu : il faut l'indiquer pour écrire ; un destinataire sans âge est considéré comme mineur.
    """
    if expediteur.is_staff:
        return None
    if Blocage.objects.filter(Q(bloqueur=expediteur, bloque=destinataire) | Q(bloqueur=destinataire, bloque=expediteur)).exists():
        return _("Vous ne pouvez pas échanger de messages : l'un de vous a bloqué l'autre.")

    profil_exp, profil_dest = profil_ou_none(expediteur), profil_ou_none(destinataire)
    if profil_exp is None or not profil_exp.annee_naissance:
        return _("Indique ton année de naissance dans ton profil pour utiliser la messagerie. Elle n'est jamais affichée.")
    if destinataire.is_staff:
        return None
    exp_majeur = profil_exp.est_majeur()
    dest_majeur = bool(profil_dest) and profil_dest.est_majeur()
    if exp_majeur != dest_majeur:
        adulte = profil_exp if exp_majeur else profil_dest
        if not (adulte and adulte.badge):
            return _("Pour protéger les plus jeunes, les messages privés entre adultes et mineurs sont réservés aux membres vérifiés par l'équipe OrientIA. Tu peux poser ta question publiquement dans la communauté.")
    return None


def masquer_si_trop_signale(objet):
    """Masque une question ou une réponse signalée par SEUIL_MASQUAGE membres différents, en attendant l'équipe."""
    nb = objet.signalements.filter(traite=False).values('auteur').distinct().count()
    if nb >= SEUIL_MASQUAGE and not objet.masque:
        objet.masque = True
        objet.save(update_fields=['masque'])
        return True
    return False
