"""Réglages de gunicorn, le serveur web de production (Linux uniquement ; sous Windows, utiliser runserver).

Lancement : gunicorn config.wsgi   (ce fichier est lu automatiquement)
"""
import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
# Processus × fils : 2 × 4 = 8 requêtes traitées en même temps (suffisant pour un petit serveur de 1 Go de mémoire)
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
worker_class = "gthread"
threads = int(os.getenv("GUNICORN_THREADS", "4"))
# Une réponse d'OrientIA (recherche + Groq) peut prendre une quinzaine de secondes : on laisse de la marge
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
# Redémarrer régulièrement les processus évite qu'une fuite de mémoire ne s'accumule
max_requests = 1000
max_requests_jitter = 100
accesslog = "-"
errorlog = "-"
