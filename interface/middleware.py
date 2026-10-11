from django.conf import settings
from django.utils import translation


class LangueProfilMiddleware:
    """Applique la langue enregistrée dans le profil quand le navigateur n'a pas encore fait de choix.

    Ex. : un élève anglophone qui se connecte depuis un nouvel ordinateur retrouve directement le site en anglais.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        langue = None
        if (request.user.is_authenticated
                and settings.LANGUAGE_COOKIE_NAME not in request.COOKIES):
            profil = getattr(request.user, 'profil', None)
            if profil is not None and profil.langue:
                langue = profil.langue
                translation.activate(langue)
                request.LANGUAGE_CODE = langue

        reponse = self.get_response(request)

        # Ne pas écraser un choix que la vue vient de faire (bouton FR/EN, accueil progressif, connexion)
        if langue and settings.LANGUAGE_COOKIE_NAME not in reponse.cookies:
            reponse.set_cookie(settings.LANGUAGE_COOKIE_NAME, langue, max_age=365 * 24 * 3600, samesite='Lax')
        return reponse
