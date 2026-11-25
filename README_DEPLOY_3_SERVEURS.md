# Déploiement sur 3 serveurs

> Guide archivé pour l’ancienne stack Django/Angular. La configuration Docker actuelle est décrite dans le [guide Odoo SOJA](odoo_soja/README.md).

Ce guide explique comment déployer le projet avec :

```text
Serveur 1 : base PostgreSQL
Serveur 2 : backend Django + Celery + Redis
Serveur 3 : frontend Angular/Nginx
```

En local, les fichiers `docker-compose.*.local.yml` simulent cette séparation. En production, le principe est identique, mais `host.docker.internal` doit être remplacé par les adresses IP privées ou les noms DNS de tes serveurs.

## 1. Architecture

Exemple d'adresses :

```text
Serveur DB       : 10.0.0.10
Serveur backend  : 10.0.0.20
Serveur frontend : 10.0.0.30
Domaine public   : ton-domaine.com
```

Flux réseau :

```text
Utilisateur
  -> https://ton-domaine.com
  -> serveur frontend Nginx
  -> serveur backend Django sur port 8000
  -> Redis local au serveur backend pour les tâches Celery
  -> serveur PostgreSQL sur port 5432
```

Le navigateur ne doit jamais parler directement à PostgreSQL.

## 2. Ports à ouvrir

Sur le serveur DB :

```text
5432 ouvert uniquement depuis l'IP du serveur backend
```

Sur le serveur backend :

```text
8000 ouvert uniquement depuis l'IP du serveur frontend
6379 fermé publiquement, utilisé seulement par Django et Celery sur le serveur backend
```

Sur le serveur frontend :

```text
80 ouvert publiquement
443 ouvert publiquement
```

En production, il est fortement recommandé de mettre HTTPS sur le serveur frontend avec Caddy, Traefik, Nginx + Certbot, ou le proxy de ton hébergeur.

## 3. Serveur 1 : PostgreSQL

Copie sur le serveur DB :

```text
docker-compose.db.local.yml
.env.local-split
```

Tu peux renommer les fichiers pour la production :

```bash
cp docker-compose.db.local.yml docker-compose.db.prod.yml
cp .env.local-split .env.db.prod
```

Dans `.env.db.prod`, garde seulement les variables utiles à PostgreSQL :

```env
POSTGRES_DB=soja
POSTGRES_USER=soja
POSTGRES_PASSWORD=mot-de-passe-tres-solide
POSTGRES_PUBLIC_PORT=5432
```

Dans `docker-compose.db.prod.yml`, le port peut rester :

```yaml
ports:
  - "${POSTGRES_PUBLIC_PORT:-5432}:5432"
```

Lancer la DB :

```bash
docker compose -f docker-compose.db.prod.yml --env-file .env.db.prod up -d
```

Vérifier :

```bash
docker compose -f docker-compose.db.prod.yml --env-file .env.db.prod ps
docker compose -f docker-compose.db.prod.yml --env-file .env.db.prod logs -f
```

## 4. Serveur 2 : backend Django, Celery et Redis

Copie sur le serveur backend :

```text
backend/
docker-compose.backend.local.yml
.env.local-split
```

Renomme pour la production :

```bash
cp docker-compose.backend.local.yml docker-compose.backend.prod.yml
cp .env.local-split .env.backend.prod
```

Dans `.env.backend.prod`, adapte les valeurs :

```env
POSTGRES_DB=soja
POSTGRES_USER=soja
POSTGRES_PASSWORD=le-meme-mot-de-passe-que-sur-la-db
POSTGRES_HOST=10.0.0.10
POSTGRES_PUBLIC_PORT=5432

DJANGO_SECRET_KEY=une-vraie-cle-secrete-longue-et-unique
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=ton-domaine.com,api.ton-domaine.com,10.0.0.20
DJANGO_CSRF_TRUSTED_ORIGINS=https://ton-domaine.com
DJANGO_CORS_ALLOWED_ORIGINS=https://ton-domaine.com

BACKEND_PUBLIC_PORT=8000
GUNICORN_WORKERS=3
GUNICORN_TIMEOUT=60

CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
CELERY_WORKER_CONCURRENCY=2
CELERY_LOG_LEVEL=info
CELERY_TASK_TIME_LIMIT=1800
CELERY_TASK_SOFT_TIME_LIMIT=1500
```

Important :

```text
POSTGRES_HOST doit être l'IP privée ou le DNS privé du serveur DB.
DJANGO_DEBUG doit rester à 0 en production.
DJANGO_SECRET_KEY ne doit jamais être la clé locale d'exemple.
Redis reste dans le même Docker Compose que Django et Celery sur le serveur backend.
```

Lancer le backend, Redis et le worker Celery :

```bash
docker compose -f docker-compose.backend.prod.yml --env-file .env.backend.prod up -d --build
```

Vérifier :

```bash
docker compose -f docker-compose.backend.prod.yml --env-file .env.backend.prod ps
docker compose -f docker-compose.backend.prod.yml --env-file .env.backend.prod logs -f
```

Au démarrage, le backend exécute automatiquement :

```text
python manage.py migrate --noinput
python manage.py collectstatic --noinput
gunicorn config.wsgi:application
```

Le worker Celery démarre dans un conteneur séparé :

```text
celery -A config worker --loglevel=info --concurrency=2
```

Pour voir seulement les logs Celery :

```bash
docker compose -f docker-compose.backend.prod.yml --env-file .env.backend.prod logs -f celery_worker
```

Pour augmenter le nombre de tâches exécutées en parallèle :

```env
CELERY_WORKER_CONCURRENCY=4
```

Pour créer une tâche lourde, ajoute une fonction dans `backend/api/tasks.py` :

```python
from celery import shared_task


@shared_task
def ma_tache_lourde(producer_id):
    # traitement long ici
    return producer_id
```

Puis appelle-la depuis Django avec :

```python
ma_tache_lourde.delay(producer_id)
```

## 5. Serveur 3 : frontend Angular/Nginx

Copie sur le serveur frontend :

```text
frontend/
docker-compose.frontend.local.yml
.env.local-split
```

Renomme pour la production :

```bash
cp docker-compose.frontend.local.yml docker-compose.frontend.prod.yml
cp .env.local-split .env.frontend.prod
```

Crée une config Nginx de production :

```bash
cp frontend/nginx.local-split.conf frontend/nginx.prod-split.conf
```

Dans `frontend/nginx.prod-split.conf`, remplace :

```nginx
proxy_pass http://host.docker.internal:8000/api/;
```

par :

```nginx
proxy_pass http://10.0.0.20:8000/api/;
```

Fais la même modification pour :

```text
/admin/
/static/
```

Donc tu dois avoir :

```nginx
location /api/ {
  proxy_pass http://10.0.0.20:8000/api/;
}

location /admin/ {
  proxy_pass http://10.0.0.20:8000/admin/;
}

location /static/ {
  proxy_pass http://10.0.0.20:8000/static/;
}
```

Ensuite, crée un Dockerfile frontend de production séparé :

```bash
cp frontend/Dockerfile.local-split frontend/Dockerfile.prod-split
```

Dans `frontend/Dockerfile.prod-split`, remplace :

```dockerfile
COPY nginx.local-split.conf /etc/nginx/conf.d/default.conf
```

par :

```dockerfile
COPY nginx.prod-split.conf /etc/nginx/conf.d/default.conf
```

Dans `docker-compose.frontend.prod.yml`, remplace :

```yaml
dockerfile: Dockerfile.local-split
```

par :

```yaml
dockerfile: Dockerfile.prod-split
```

Dans `.env.frontend.prod` :

```env
FRONTEND_PUBLIC_PORT=80
```

Lancer le frontend :

```bash
docker compose -f docker-compose.frontend.prod.yml --env-file .env.frontend.prod up -d --build
```

Vérifier :

```bash
docker compose -f docker-compose.frontend.prod.yml --env-file .env.frontend.prod ps
docker compose -f docker-compose.frontend.prod.yml --env-file .env.frontend.prod logs -f
```

Ouvrir :

```text
http://ton-domaine.com
```

ou, après configuration HTTPS :

```text
https://ton-domaine.com
```

## 6. Ordre de démarrage

Démarre toujours dans cet ordre :

```bash
# Serveur DB
docker compose -f docker-compose.db.prod.yml --env-file .env.db.prod up -d

# Serveur backend
docker compose -f docker-compose.backend.prod.yml --env-file .env.backend.prod up -d --build

# Serveur frontend
docker compose -f docker-compose.frontend.prod.yml --env-file .env.frontend.prod up -d --build
```

## 7. Mise à jour du code

Si tu modifies le backend :

```bash
docker compose -f docker-compose.backend.prod.yml --env-file .env.backend.prod up -d --build
```

Cette commande reconstruit aussi l'image utilisée par le worker Celery.

Si tu modifies le frontend :

```bash
docker compose -f docker-compose.frontend.prod.yml --env-file .env.frontend.prod up -d --build
```

Si tu modifies seulement la DB ou les variables PostgreSQL :

```bash
docker compose -f docker-compose.db.prod.yml --env-file .env.db.prod up -d
```

## 8. Sauvegarde PostgreSQL

Sur le serveur DB :

```bash
docker compose -f docker-compose.db.prod.yml --env-file .env.db.prod exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup.sql
```

Restaurer :

```bash
docker compose -f docker-compose.db.prod.yml --env-file .env.db.prod exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB" < backup.sql
```

## 9. Checklist production

Avant d'ouvrir au public :

```text
DJANGO_DEBUG=0
DJANGO_SECRET_KEY remplacée
POSTGRES_PASSWORD remplacé
PostgreSQL accessible seulement depuis le backend
Backend accessible seulement depuis le frontend
Redis non exposé publiquement
Celery worker actif sur le serveur backend
Frontend accessible en HTTPS
DJANGO_ALLOWED_HOSTS contient le domaine public
DJANGO_CSRF_TRUSTED_ORIGINS contient https://ton-domaine.com
DJANGO_CORS_ALLOWED_ORIGINS contient https://ton-domaine.com
Sauvegarde PostgreSQL testée
```

## 10. Différence avec le local

En local, on utilise :

```text
host.docker.internal
localhost:5433
localhost:8000
localhost:8080
```

Sur tes vrais serveurs, on utilise plutôt :

```text
IP privée DB       : 10.0.0.10
IP privée backend  : 10.0.0.20
Domaine frontend   : ton-domaine.com
```

La logique reste la même : seul le nom des machines change.
