"""Cœur d'OrientIA : recherche dans les documents officiels, puis rédaction de la réponse par Groq."""
import logging
import operator
import re
from functools import reduce
from pathlib import Path

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import Q

from .ia import generer_texte, mots_cles_recherche
from .models import DocumentChunk

logger = logging.getLogger(__name__)

# Configuration de recherche PostgreSQL créée par la migration rag 0005 :
# dictionnaire français + suppression des accents (« ecole » trouve « école »)
CONFIG_RECHERCHE = "french_unaccent"

# Nombre d'échanges précédents rappelés à OrientIA pour comprendre les questions de suivi
ECHANGES_MEMORISES = 3
LONGUEUR_MAX_REPONSE_MEMORISEE = 1200


def rechercher_chunks_pertinents(question, nombre=8, question_precedente=""):
    """Trouve les passages des documents officiels qui répondent le mieux à la question.

    Recherche plein texte de PostgreSQL (dictionnaire français : « écoles » trouve « école »),
    avec la question + les mots-clés français proposés par Groq (utile pour les questions en anglais).
    """
    try:
        mots = mots_cles_recherche(question, question_precedente)
    except Exception:
        logger.warning("Mots-clés indisponibles, recherche avec la question seule", exc_info=True)
        mots = []

    termes = [question] + mots
    requete = reduce(operator.or_, (SearchQuery(t, config=CONFIG_RECHERCHE, search_type="plain") for t in termes))
    # Chaque mot-clé compte séparément : une requête « mot1 OU mot2 OU ... »
    for mot in mots:
        for morceau in mot.split():
            requete |= SearchQuery(morceau, config=CONFIG_RECHERCHE)

    resultats = list(
        DocumentChunk.objects
        .annotate(rang=SearchRank("recherche", requete))
        .filter(rang__gt=0)
        .order_by("-rang")[:nombre]
    )
    if resultats:
        return resultats

    # Rien trouvé : on se rabat sur une recherche simple par mot
    filtre = reduce(operator.or_, (Q(contenu__unaccent__icontains=m) for m in mots or question.split()), Q(pk__in=[]))
    return list(DocumentChunk.objects.filter(filtre)[:nombre])


def titre_source(nom_fichier):
    """« Guide_Orientation_Post_Bac_Cameroun.pdf » → « Guide Orientation Post Bac Cameroun »."""
    return re.sub(r"[_\s]+", " ", Path(nom_fichier).stem).strip()


def sources_de(chunks):
    """Documents consultés pour la réponse, sans doublon, dans l'ordre de pertinence."""
    return list(dict.fromkeys(titre_source(c.source) for c in chunks))


CONSIGNE_ANGLAIS = """IMPORTANT : l'élève est anglophone. Réponds UNIQUEMENT en anglais (même si le contexte est en français),
et pense au sous-système anglophone camerounais (GCE O/A Level, HND, universités de Buea et de Bamenda) quand c'est pertinent.
"""


def decrire_profil(profil):
    """Résume le profil de l'élève pour qu'OrientIA personnalise sa réponse."""
    if profil is None:
        return ""
    lignes = []
    if profil.sous_systeme:
        lignes.append(f"- Sous-système : {'anglophone (GCE)' if profil.sous_systeme == 'anglophone' else 'francophone (Baccalauréat)'}")
    if profil.serie_bac:
        lignes.append(f"- Série du bac : {profil.get_serie_bac_display()}")
    if profil.centres_interet:
        lignes.append(f"- Centres d'intérêt : {profil.centres_interet}")
    if profil.region:
        lignes.append(f"- Région : {profil.region}")
    if profil.projet_etudes:
        lignes.append(f"- Ce qu'il/elle aimerait faire ensuite : {profil.projet_etudes}")
    if profil.ecole_souhaitee:
        lignes.append(f"- École visée : {profil.ecole_souhaitee}")
    texte = ""
    if lignes:
        texte = "Profil de l'élève (adapte tes conseils à ce profil quand c'est pertinent) :\n" + "\n".join(lignes) + "\n\n"
    # Écoles les plus proches qui proposent les domaines qui intéressent l'élève
    from orientation.services import resume_pour_orientia
    return texte + resume_pour_orientia(profil)


def bloc_document(document, nom_document):
    """Document joint par l'élève (relevé de notes, emploi du temps, brochure d'école...)."""
    if not document:
        return ""
    return (f"L'élève a joint un document « {nom_document} ». Voici son contenu : appuie-toi dessus pour répondre "
            f"(il complète les documents officiels) :\n<<<\n{document}\n>>>\n\n")


def bloc_historique(historique):
    """Début de la conversation : permet de comprendre « et pour la 2e filière ? »."""
    if not historique:
        return ""
    lignes = []
    for question, reponse in historique[-ECHANGES_MEMORISES:]:
        if len(reponse) > LONGUEUR_MAX_REPONSE_MEMORISEE:
            reponse = reponse[:LONGUEUR_MAX_REPONSE_MEMORISEE] + "…"
        lignes.append(f"Élève : {question}\nOrientIA : {reponse}")
    return ("Début de la conversation (sers-t'en pour comprendre la nouvelle question si elle y fait référence) :\n"
            + "\n\n".join(lignes) + "\n\n")


def generer_reponse(question, chunks, profil=None, langue="fr", document="", nom_document="", historique=None):
    """Construit un prompt avec le contexte trouvé (et le profil de l'élève s'il est connecté), puis demande la réponse.

    langue : "fr" ou "en" — OrientIA répond dans la langue de l'élève (francophone ou anglophone).
    historique : liste de (question, réponse) des échanges précédents de la même conversation.
    """
    contexte = "\n\n---\n\n".join(f"[Source : {c.source}]\n{c.contenu}" for c in chunks)

    prompt = f"""Tu es OrientIA, l'assistant d'orientation académique pour les bacheliers camerounais.
Tu tutoies l'élève, avec un ton chaleureux et encourageant.
Réponds à la question en te basant UNIQUEMENT sur le contexte ci-dessous : ce sont des extraits des documents
officiels d'OrientIA (programmes du MINESUP, guides d'orientation, liste des établissements). Ne dis pas que l'élève
te les a fournis. Cite toutes les options pertinentes trouvées dans le contexte, pas seulement la première.
Si le contexte ne permet pas de répondre, dis-le clairement plutôt que d'inventer une réponse, et conseille
de vérifier auprès de l'établissement ou du MINESUP.
Ne fais aucun calcul et n'additionne pas de chiffres pour obtenir un total (crédits, heures, frais...) : cite
uniquement les nombres tels qu'ils apparaissent dans le contexte, en précisant à quoi ils correspondent.
Mise en forme : paragraphes courts, listes à puces et **gras** autorisés ; pas de tableaux.
{CONSIGNE_ANGLAIS if langue == "en" else ""}
{decrire_profil(profil)}{bloc_historique(historique)}{bloc_document(document, nom_document)}Contexte :
{contexte}

Question : {question}

Réponse :"""

    return generer_texte(prompt)
