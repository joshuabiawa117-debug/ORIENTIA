"""Stockage des fichiers envoyés (annales) sur Vercel Blob, car le disque de Vercel est en lecture seule.

Activé automatiquement quand BLOB_READ_WRITE_TOKEN est défini (voir config/settings.py).
"""
import mimetypes
import re
import urllib.request

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


def url_base_du_store():
    """Adresse publique du store : BLOB_URL_BASE, sinon déduite du jeton (vercel_blob_rw_<identifiant>_<secret>)."""
    if settings.BLOB_URL_BASE:
        return settings.BLOB_URL_BASE
    import os
    trouve = re.match(r"vercel_blob_rw_([A-Za-z0-9]+)_", os.getenv("BLOB_READ_WRITE_TOKEN", ""))
    if not trouve:
        raise RuntimeError("Indique BLOB_URL_BASE (adresse publique du Blob store) dans les variables Vercel.")
    return f"https://{trouve.group(1).lower()}.public.blob.vercel-storage.com"


@deconstructible
class VercelBlobStorage(Storage):

    def client(self):
        from vercel.blob import BlobClient
        return BlobClient()

    def _save(self, name, content):
        type_mime = getattr(content, "content_type", None) or mimetypes.guess_type(name)[0]
        # Suffixe aléatoire : deux annales du même nom ne s'écrasent jamais
        resultat = self.client().put(name.replace("\\", "/"), content.read(), access="public",
                                     content_type=type_mime, add_random_suffix=True)
        return resultat.pathname

    def _open(self, name, mode="rb"):
        with urllib.request.urlopen(self.url(name), timeout=30) as reponse:
            return ContentFile(reponse.read(), name=name)

    def exists(self, name):
        return False  # le suffixe aléatoire garantit un nom unique

    def delete(self, name):
        if name:
            self.client().delete(self.url(name))

    def size(self, name):
        return self.client().head(self.url(name)).size

    def url(self, name):
        return f"{url_base_du_store()}/{name.lstrip('/')}"
