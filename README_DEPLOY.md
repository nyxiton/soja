# Déploiement serveur

La configuration Docker actuelle lance Odoo SOJA. Consultez [le guide Odoo SOJA](odoo_soja/README.md) pour le démarrage. Les instructions Django/Angular ci-dessous concernent l’ancienne stack et sont conservées à titre d’archive.

Ce projet peut être transporté sur un serveur avec Docker Compose.

## Mode local séparé en 3 services

Cette configuration simule en local un déploiement avec la base, le backend et le frontend lancés séparément, comme s'ils étaient sur trois serveurs différents. Le service backend lance aussi Redis et un worker Celery pour les tâches lourdes.

Les fichiers utilisés sont :

```text
docker-compose.db.local.yml
docker-compose.backend.local.yml
docker-compose.frontend.local.yml
.env.local-split
frontend/nginx.local-split.conf
```

Lancer la base PostgreSQL :

```bash
docker compose -f docker-compose.db.local.yml --env-file .env.local-split up -d
```

Lancer le backend Django, Redis et Celery :

```bash
docker compose -f docker-compose.backend.local.yml --env-file .env.local-split up -d --build
```

Lancer le frontend Angular/Nginx :

```bash
docker compose -f docker-compose.frontend.local.yml --env-file .env.local-split up -d --build
```

Ouvrir ensuite :

```text
http://localhost:8080/
```

Dans ce mode :

```text
PostgreSQL local : localhost:5433
Backend Django : http://localhost:8000
Redis : interne au compose backend
Celery : worker interne au compose backend
Frontend : http://localhost:8080
```

## Mode local Odoo

Un stack Odoo autonome est disponible dans `odoo_soja`. Il lance Odoo avec une base PostgreSQL dediee et installe le module `SOJA Management`, qui reprend les objets metier du projet : producteurs, parcelles GPS, semence, recolte, cooperative, usine et banque.

Lancer Odoo :

```bash
docker compose -f docker-compose.odoo.local.yml up -d
```

Ouvrir ensuite :

```text
http://localhost:8069/
```

Interface SOJA dans Odoo, avec le design et les ecrans du frontend :

```text
http://localhost:8069/soja
```

Dans ce mode :

```text
Odoo : http://localhost:8069
Interface SOJA Odoo : http://localhost:8069/soja
PostgreSQL Odoo : localhost:5434
Base Odoo initialisee : odoo_soja
Module : SOJA Management
```

Voir les logs :

```bash
docker compose -f docker-compose.db.local.yml --env-file .env.local-split logs -f
docker compose -f docker-compose.backend.local.yml --env-file .env.local-split logs -f
docker compose -f docker-compose.frontend.local.yml --env-file .env.local-split logs -f
```

Voir seulement les logs Celery :

```bash
docker compose -f docker-compose.backend.local.yml --env-file .env.local-split logs -f celery_worker
```

Arrêter les trois services :

```bash
docker compose -f docker-compose.frontend.local.yml --env-file .env.local-split down
docker compose -f docker-compose.backend.local.yml --env-file .env.local-split down
docker compose -f docker-compose.db.local.yml --env-file .env.local-split down
```

Supprimer aussi les données locales PostgreSQL :

```bash
docker compose -f docker-compose.db.local.yml --env-file .env.local-split down -v
```

## 1. Préparer le serveur

Installer Docker et Docker Compose, puis copier tout le dossier du projet sur le serveur.

Créer le fichier `.env` depuis l'exemple :

```bash
cp .env.example .env
```

Modifier au minimum :

```env
POSTGRES_PASSWORD=un-mot-de-passe-solide
DJANGO_SECRET_KEY=une-cle-secrete-longue
DJANGO_ALLOWED_HOSTS=ton-domaine.com,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://ton-domaine.com
HTTP_PORT=80
```

Pour tester sans domaine, garder `localhost,127.0.0.1` et utiliser l'IP du serveur dans `DJANGO_ALLOWED_HOSTS`.

## 2. Lancer en production

```bash
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

Le frontend Angular est servi par Nginx. Les appels `/api/` sont proxifiés vers Django.

## 3. Vérifier

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f frontend
```

Ouvrir :

```text
http://ton-domaine.com/
```

ou :

```text
http://IP_DU_SERVEUR/
```

## 4. Migrations

Les migrations sont lancées automatiquement au démarrage du backend. Pour les relancer manuellement :

```bash
docker compose -f docker-compose.prod.yml exec backend python manage.py migrate
```

## 5. Sauvegarde base PostgreSQL

Créer une sauvegarde :

```bash
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup.sql
```

Restaurer une sauvegarde :

```bash
docker compose -f docker-compose.prod.yml exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB" < backup.sql
```

## 6. Mise à jour

Après modification du code :

```bash
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

## 7. HTTPS

Pour HTTPS, placer ce stack derrière un reverse proxy comme Caddy, Traefik ou Nginx avec Certbot.

Dans ce cas :

```env
DJANGO_ALLOWED_HOSTS=ton-domaine.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://ton-domaine.com
HTTP_PORT=127.0.0.1:8080
```

Puis le reverse proxy public redirige vers `127.0.0.1:8080`.
