"""Raccourci conservé pour l'habitude : équivaut à « python manage.py indexer_documents »."""
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.core.management import call_command  # noqa: E402

call_command("indexer_documents")
