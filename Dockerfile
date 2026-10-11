# Image de production d'OrientIA : fonctionne chez tout hébergeur qui accepte Docker
# (Render, Railway, Fly.io, un VPS...). Les bibliothèques géographiques (GDAL) sont incluses.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# GDAL/GEOS/PROJ pour PostGIS (cartes, écoles proches) et pg_dump pour les sauvegardes
RUN apt-get update \
    && apt-get install -y --no-install-recommends gdal-bin postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Traductions anglaises et fichiers statiques préparés dès la construction
# (valeurs factices : aucune connexion à la base n'est nécessaire pour ces deux étapes)
RUN DJANGO_SECRET_KEY=construction DB_PASSWORD=construction python manage.py compiler_traductions \
    && DJANGO_SECRET_KEY=construction DB_PASSWORD=construction python manage.py collectstatic --noinput

# Utilisateur sans droits d'administration : limite les dégâts en cas de faille
RUN useradd --create-home orientia && mkdir -p /app/logs /app/media /app/sauvegardes \
    && chown -R orientia /app/logs /app/media /app/sauvegardes /app/locale
USER orientia

EXPOSE 8000
# Au démarrage : mise à jour de la base, table du cache, puis le serveur web
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py createcachetable && gunicorn config.wsgi"]
