from django.conf import settings


def reglages_site(request):
    """Réglages utiles à toutes les pages : fond de carte (modifiable dans config/.env)."""
    return {
        'taille_max_envoi_mo': settings.TAILLE_MAX_ENVOI_MO,
        'tuiles_carte': {
            'url': settings.CARTE_TUILES_URL,
            'attribution': settings.CARTE_TUILES_ATTRIBUTION,
        },
    }
