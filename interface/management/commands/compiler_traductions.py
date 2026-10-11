"""Génère les fichiers de traduction anglaise sans avoir besoin de GNU gettext.

Usage : python manage.py compiler_traductions

1. Repère tous les textes à traduire : {% translate %}, {% blocktranslate %}, {{ _("...") }} dans les templates,
   et _("...") / gettext_lazy("...") dans le code Python.
2. Prend leur traduction dans interface/traductions_en.py (dictionnaire français → anglais).
3. Écrit locale/en/LC_MESSAGES/django.po puis le compile en django.mo (lu par Django).
Les textes sans traduction sont signalés : ils restent affichés en français.
"""
import ast
import re
from pathlib import Path

import polib
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.translation.template import templatize

from interface.traductions_en import TRADUCTIONS

DOSSIERS_PYTHON = ['interface', 'orientation', 'communaute', 'espace', 'rag', 'etablissements', 'config']
FICHIERS_PYTHON = ['poser_question.py']
FONCTIONS = {'_', '_g', '_l', 'gettext', 'gettext_lazy', 'pgettext'}
RE_APPEL = re.compile(r"""\b(?:gettext|_)\((u?(?:'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"))\)""")


def textes_des_templates(base):
    textes = {}
    for chemin in sorted((base / 'templates').rglob('*.html')):
        code = templatize(chemin.read_text(encoding='utf-8'))
        for litteral in RE_APPEL.findall(code):
            textes.setdefault(ast.literal_eval(litteral.lstrip('u')), str(chemin.relative_to(base)))
    return textes


def textes_python(base):
    textes = {}
    fichiers = [base / f for f in FICHIERS_PYTHON]
    for dossier in DOSSIERS_PYTHON:
        fichiers += [f for f in (base / dossier).rglob('*.py') if 'migrations' not in f.parts]
    for chemin in fichiers:
        arbre = ast.parse(chemin.read_text(encoding='utf-8'))
        for noeud in ast.walk(arbre):
            if (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Name) and noeud.func.id in FONCTIONS
                    and noeud.args and isinstance(noeud.args[0], ast.Constant) and isinstance(noeud.args[0].value, str)):
                textes.setdefault(noeud.args[0].value, str(chemin.relative_to(base)))
    return textes


class Command(BaseCommand):
    help = "Compile les traductions anglaises (interface/traductions_en.py → locale/en/LC_MESSAGES/django.mo)."

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        textes = {**textes_python(base), **textes_des_templates(base)}

        po = polib.POFile()
        po.metadata = {
            'Content-Type': 'text/plain; charset=UTF-8',
            'Language': 'en',
            'Plural-Forms': 'nplurals=2; plural=(n != 1);',
        }
        manquants = []
        for msgid, origine in sorted(textes.items()):
            traduction = TRADUCTIONS.get(msgid, '')
            if not traduction:
                manquants.append((origine, msgid))
            po.append(polib.POEntry(msgid=msgid, msgstr=traduction, occurrences=[(origine, '')]))

        dossier = base / 'locale' / 'en' / 'LC_MESSAGES'
        dossier.mkdir(parents=True, exist_ok=True)
        po.save(str(dossier / 'django.po'))
        po.save_as_mofile(str(dossier / 'django.mo'))

        inutilises = set(TRADUCTIONS) - set(textes)
        self.stdout.write(self.style.SUCCESS(f"{len(textes) - len(manquants)}/{len(textes)} textes traduits en anglais."))
        for origine, msgid in manquants:
            self.stdout.write(self.style.WARNING(f"  À traduire ({origine}) : {msgid!r}"))
        if inutilises:
            self.stdout.write(f"  {len(inutilises)} traduction(s) inutilisée(s) dans traductions_en.py.")
