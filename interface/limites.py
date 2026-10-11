"""Limites d'utilisation par heure : protègent le quota Groq et la communauté contre les abus.

Un visiteur est reconnu à son adresse IP, un élève connecté à son compte.
Les compteurs sont gardés dans le cache de Django (table « orientia_cache »), partagé par tous les processus.
"""
import time

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils.translation import gettext as _


def adresse_ip(request):
    """Adresse du visiteur. Derrière un hébergeur (proxy), la vraie adresse est dans X-Forwarded-For."""
    if settings.DERRIERE_PROXY:
        transmise = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if transmise:
            return transmise.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def limite_atteinte(request, action):
    """Compte une utilisation de « action ».

    Renvoie None si c'est autorisé, sinon le nombre de minutes avant de pouvoir recommencer.
    """
    visiteur, connecte = settings.LIMITES_PAR_HEURE[action]
    if request.user.is_authenticated:
        maximum, qui = connecte, f"u{request.user.pk}"
    else:
        maximum, qui = visiteur, f"ip{adresse_ip(request)}"

    maintenant = time.time()
    cle = f"limite:{action}:{qui}:{int(maintenant // 3600)}"
    cache.add(cle, 0, timeout=3600)
    try:
        compteur = cache.incr(cle)
    except ValueError:  # la clé vient d'expirer
        cache.set(cle, 1, timeout=3600)
        compteur = 1
    if compteur > maximum:
        return max(1, 60 - int(maintenant % 3600) // 60)
    return None


def message_limite(request, minutes):
    if request.user.is_authenticated:
        return _("Tu as beaucoup utilisé OrientIA cette heure-ci. Réessaie dans %(minutes)s min.") % {"minutes": minutes}
    return _("Limite atteinte pour les visiteurs. Réessaie dans %(minutes)s min, ou crée un compte gratuit pour en profiter davantage.") % {"minutes": minutes}


def reponse_limite(request, minutes):
    """Réponse JSON « trop de demandes » (code 429) pour les appels en arrière-plan."""
    return JsonResponse({"erreur": message_limite(request, minutes)}, status=429)
