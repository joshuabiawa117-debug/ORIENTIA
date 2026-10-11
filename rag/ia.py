"""Appels à l'IA d'OrientIA, via l'API Groq (très rapide, compatible OpenAI)."""
import json
import logging
import os
from functools import cache

import groq
from groq import Groq

logger = logging.getLogger(__name__)

# Modèles Groq utilisés (modifiables dans config/.env sans toucher au code)
MODELE_CHAT = os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-120b")      # réponses d'OrientIA et quiz
MODELE_RAPIDE = os.getenv("GROQ_FAST_MODEL", "openai/gpt-oss-20b")     # petites tâches (mots-clés de recherche)
# Modèle de remplacement si le modèle principal est en panne, saturé ou retiré par Groq
MODELE_SECOURS = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")


@cache
def client():
    """Crée le client au premier appel (lit la clé GROQ_API_KEY dans config/.env)."""
    return Groq(api_key=os.environ["GROQ_API_KEY"])


def completion(modele, **options):
    """Appelle le modèle demandé ; en cas d'erreur de Groq, réessaie une fois avec le modèle de secours."""
    try:
        return client().chat.completions.create(model=modele, **options)
    except groq.AuthenticationError:
        raise  # clé invalide : un autre modèle n'y changera rien
    except groq.APIError:
        if not MODELE_SECOURS or MODELE_SECOURS == modele:
            raise
        logger.warning("Modèle %s indisponible, bascule sur %s", modele, MODELE_SECOURS, exc_info=True)
        return client().chat.completions.create(model=MODELE_SECOURS, **options)


def generer_texte(prompt):
    """Envoie un prompt au modèle de chat et renvoie sa réponse."""
    reponse = completion(
        MODELE_CHAT,
        messages=[{"role": "user", "content": prompt}],
        reasoning_effort="low",
    )
    return reponse.choices[0].message.content


def generer_json(prompt, modele=None):
    """Comme generer_texte, mais force le modèle à répondre avec un objet JSON valide."""
    reponse = completion(
        modele or MODELE_CHAT,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        reasoning_effort="low",
    )
    return reponse.choices[0].message.content


def mots_cles_recherche(question, question_precedente=""):
    """Transforme une question (en français ou en anglais) en mots-clés français.

    Les documents officiels sont en français : un élève anglophone qui demande
    « Which schools teach computer science? » doit retrouver « informatique », « école »...
    La question précédente permet de comprendre une question de suivi (« et pour la 2e ? »).
    """
    suivi = ""
    if question_precedente:
        suivi = (f"Question précédente de l'élève, pour comprendre une question de suivi : "
                 f"« {question_precedente[:500]} »\n")
    prompt = f"""Tu aides à chercher dans des documents officiels camerounais d'orientation post-bac, rédigés en FRANÇAIS
(BTS, filières, établissements privés IPES, débouchés selon les séries du bac).
{suivi}Question de l'élève (peut être en anglais) : « {question} »

Donne 4 à 8 mots-clés ou expressions courtes EN FRANÇAIS pour retrouver les passages utiles,
avec les synonymes probables (ex. « computer science » → informatique, génie logiciel).
Réponds UNIQUEMENT en JSON : {{"mots": ["...", "..."]}}"""
    mots = json.loads(generer_json(prompt, modele=MODELE_RAPIDE)).get("mots", [])
    return [str(m).strip() for m in mots if str(m).strip()][:8]


# ---------- Voix, fichiers et images ----------

MODELE_VISION = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")       # lit les photos (emploi du temps, documents)
MODELE_TRANSCRIPTION = os.getenv("GROQ_AUDIO_MODEL", "whisper-large-v3-turbo")

TAILLE_MAX_FICHIER = 8 * 1024 * 1024   # 8 Mo
LONGUEUR_MAX_TEXTE = 12000             # caractères gardés d'un document joint
TYPES_IMAGE = {"image/png", "image/jpeg", "image/webp", "image/gif"}


class FichierRefuse(ValueError):
    """Fichier trop lourd ou d'un type qu'OrientIA ne sait pas lire."""


# Sur un enregistrement silencieux, Whisper « entend » des génériques de vidéos (défaut connu du modèle)
PHRASES_FANTOMES_CONTENANT = ("radio-canada", "amara.org", "sous-titrage", "sous-titres réalisés", "merci d'avoir regardé",
                              "thanks for watching", "thank you for watching", "abonnez-vous", "please subscribe")
PHRASES_FANTOMES_EXACTES = {"you", "thank you", "merci.", "...", "…", "bye", "music"}


def est_phrase_fantome(texte):
    propre = texte.strip().lower()
    return (not propre or propre.strip(" .!") in PHRASES_FANTOMES_EXACTES or propre in PHRASES_FANTOMES_EXACTES
            or any(marque in propre for marque in PHRASES_FANTOMES_CONTENANT))


def transcrire_audio(fichier, langue=None):
    """Transforme un enregistrement vocal en texte (Whisper, sur Groq). Renvoie "" si rien n'a été dit."""
    reponse = client().audio.transcriptions.create(
        file=(fichier.name or "voix.webm", fichier.read()),
        model=MODELE_TRANSCRIPTION,
        language=langue,
        response_format="json",
    )
    texte = reponse.text.strip()
    return "" if est_phrase_fantome(texte) else texte


def appel_vision(consigne, image_octets, type_mime, json_attendu=False):
    """Envoie une image et une consigne au modèle de vision."""
    import base64
    image = f"data:{type_mime};base64,{base64.b64encode(image_octets).decode()}"
    options = {"response_format": {"type": "json_object"}} if json_attendu else {}
    reponse = client().chat.completions.create(
        model=MODELE_VISION,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": consigne},
            {"type": "image_url", "image_url": {"url": image}},
        ]}],
        **options,
    )
    return reponse.choices[0].message.content


def lire_fichier(fichier):
    """Renvoie (texte, est_image, octets, type_mime) d'un fichier envoyé : PDF, texte ou image."""
    if fichier.size > TAILLE_MAX_FICHIER:
        raise FichierRefuse("trop_lourd")
    nom = (fichier.name or "").lower()
    type_mime = (fichier.content_type or "").lower()
    octets = fichier.read()

    if type_mime in TYPES_IMAGE or nom.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "", True, octets, type_mime if type_mime in TYPES_IMAGE else "image/jpeg"
    if nom.endswith(".pdf") or type_mime == "application/pdf":
        from io import BytesIO
        from pypdf import PdfReader
        texte = "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(octets)).pages)
        return texte[:LONGUEUR_MAX_TEXTE], False, octets, "application/pdf"
    if nom.endswith((".txt", ".md", ".csv")) or type_mime.startswith("text/"):
        return octets.decode("utf-8", errors="replace")[:LONGUEUR_MAX_TEXTE], False, octets, "text/plain"
    raise FichierRefuse("type")


def texte_du_fichier(fichier):
    """Contenu lisible d'un fichier : son texte, ou la transcription de l'image par le modèle de vision."""
    texte, est_image, octets, type_mime = lire_fichier(fichier)
    if est_image:
        texte = appel_vision(
            "Transcris fidèlement tout le texte visible sur cette image (tableaux compris, ligne par ligne), "
            "puis décris en une phrase ce que montre l'image.", octets, type_mime)
    return texte.strip()


CONSIGNE_CRENEAUX = """Extrais de ce contenu les créneaux d'un emploi du temps hebdomadaire.
- "cours" : un cours ou une activité fixe (avec la matière dans "intitule").
- "dispo" : un moment où l'élève dit être libre / disponible pour réviser.
Jours : 0 = lundi, 1 = mardi, 2 = mercredi, 3 = jeudi, 4 = vendredi, 5 = samedi, 6 = dimanche.
Heures au format HH:MM sur 24 h (ex. « 14h » → "14:00", « le soir » → 18:00-21:00, « le matin » → 08:00-12:00).
Réponds UNIQUEMENT en JSON : {"creneaux": [{"type": "cours", "jour": 0, "debut": "08:00", "fin": "10:00", "intitule": "Mathématiques"}]}"""


def extraire_creneaux(texte="", image=None):
    """Liste de créneaux (dict) lus dans un texte ou une photo d'emploi du temps."""
    if image:
        octets, type_mime = image
        brut = appel_vision(CONSIGNE_CRENEAUX, octets, type_mime, json_attendu=True)
    else:
        brut = generer_json(CONSIGNE_CRENEAUX + "\n\nContenu :\n" + texte[:LONGUEUR_MAX_TEXTE])
    donnees = json.loads(brut)
    if isinstance(donnees, dict):
        donnees = donnees.get("creneaux") or next((v for v in donnees.values() if isinstance(v, list)), [])
    return donnees if isinstance(donnees, list) else []
