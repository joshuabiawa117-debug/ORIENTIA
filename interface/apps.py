from django.apps import AppConfig


class InterfaceConfig(AppConfig):
    name = 'interface'

    def ready(self):
        from . import signals  # noqa: F401 — enregistre la création automatique du profil
