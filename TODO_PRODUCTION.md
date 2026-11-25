# TODO mise en production

Liste des points à terminer avant un vrai déploiement public.

## Priorité 1 : sécurité indispensable

- [ ] Ajouter une authentification pour l'API Django.
- [ ] Retirer ou limiter les endpoints publics en écriture.
- [ ] Remplacer les vues `@csrf_exempt` par une stratégie propre : session Django, token API, JWT ou autre.
- [ ] Vérifier que seuls les utilisateurs autorisés peuvent créer, modifier et supprimer des producteurs.
- [ ] Créer de vrais fichiers `.env` de production, séparés par serveur.
- [ ] Remplacer `DJANGO_SECRET_KEY` par une vraie clé longue et unique.
- [ ] Remplacer `POSTGRES_PASSWORD` par un mot de passe fort.
- [ ] Mettre `DJANGO_DEBUG=0`.
- [ ] Configurer `DJANGO_ALLOWED_HOSTS` avec le vrai domaine.
- [ ] Configurer `DJANGO_CSRF_TRUSTED_ORIGINS` avec `https://ton-domaine.com`.
- [ ] Configurer `DJANGO_CORS_ALLOWED_ORIGINS` avec `https://ton-domaine.com`.

## Priorité 2 : HTTPS et réseau

- [ ] Mettre HTTPS sur le serveur frontend.
- [ ] Choisir la solution HTTPS : Caddy, Traefik, Nginx + Certbot, ou proxy hébergeur.
- [ ] Rediriger automatiquement HTTP vers HTTPS.
- [ ] Vérifier que le frontend fonctionne en `https://`.
- [ ] Vérifier que les appels `/api/`, `/admin/` et `/static/` passent bien du frontend vers le backend.
- [ ] Configurer le firewall du serveur DB : port `5432` accessible seulement depuis le serveur backend.
- [ ] Configurer le firewall du serveur backend : port `8000` accessible seulement depuis le serveur frontend.
- [ ] Vérifier que Redis n'est jamais exposé publiquement.
- [ ] Garder seulement les ports `80` et `443` publics sur le serveur frontend.
- [ ] Limiter l'accès SSH si possible.

## Priorité 3 : sauvegardes PostgreSQL

- [ ] Créer un script de sauvegarde PostgreSQL.
- [ ] Planifier une sauvegarde automatique quotidienne.
- [ ] Stocker les sauvegardes hors du serveur DB.
- [ ] Ajouter une rétention des sauvegardes, par exemple 7 ou 30 jours.
- [ ] Tester une restauration complète depuis un fichier `backup.sql`.
- [ ] Documenter la procédure de restauration.

## Priorité 4 : photos et fichiers

- [ ] Remplacer le stockage base64 des photos dans PostgreSQL.
- [ ] Ajouter un stockage fichier : volume Docker, dossier persistant, S3, MinIO ou autre stockage objet.
- [ ] Garder seulement l'URL ou le chemin de la photo en base.
- [ ] Prévoir une limite de taille d'image.
- [ ] Prévoir une compression/redimensionnement des images avant stockage.
- [ ] Sauvegarder aussi le stockage des photos.

## Priorité 5 : Docker production

- [ ] Modifier `backend/Dockerfile.prod` pour exécuter Django avec un utilisateur non-root.
- [ ] Modifier le worker Celery pour utiliser aussi un utilisateur non-root.
- [ ] Vérifier que les permissions de fichiers restent correctes après passage non-root.
- [ ] Ajouter des healthchecks pour le backend.
- [ ] Ajouter des healthchecks pour Redis.
- [ ] Ajouter des healthchecks pour le frontend.
- [ ] Éviter de builder directement sur le serveur à long terme.
- [ ] Préparer des images Docker versionnées.
- [ ] Prévoir une stratégie de rollback.

## Priorité 6 : Celery et tâches lourdes

- [ ] Identifier les traitements longs à déplacer dans Celery.
- [ ] Créer les vraies tâches dans `backend/api/tasks.py` ou dans des modules dédiés.
- [ ] Ajouter une gestion des erreurs dans les tâches Celery.
- [ ] Ajouter des logs utiles dans les tâches Celery.
- [ ] Surveiller les tâches échouées.
- [ ] Décider si le résultat des tâches doit être stocké en base ou seulement dans Redis.
- [ ] Ajuster `CELERY_WORKER_CONCURRENCY` selon la taille du serveur backend.
- [ ] Ajuster `CELERY_TASK_TIME_LIMIT` et `CELERY_TASK_SOFT_TIME_LIMIT`.

## Priorité 7 : logs et monitoring

- [ ] Mettre en place une rotation des logs Docker.
- [ ] Centraliser les logs si possible.
- [ ] Surveiller les conteneurs : frontend, backend, celery_worker, redis, db.
- [ ] Ajouter une alerte si un conteneur tombe.
- [ ] Ajouter une alerte si PostgreSQL devient indisponible.
- [ ] Ajouter une alerte si Redis devient indisponible.
- [ ] Ajouter une alerte si Celery ne consomme plus les tâches.
- [ ] Ajouter une route de santé backend déjà disponible via `/api/health/` si elle est exposée dans les URLs.

## Priorité 8 : tests avant production

- [ ] Ajouter des tests backend pour la création de producteur.
- [ ] Ajouter des tests backend pour la modification de producteur.
- [ ] Ajouter des tests backend pour la suppression de producteur.
- [ ] Ajouter des tests backend pour les informations récolte/semence.
- [ ] Ajouter des tests backend pour les données coopérative.
- [ ] Ajouter des tests backend pour les données usine.
- [ ] Ajouter des tests backend pour les données banque.
- [ ] Ajouter un test Celery simple.
- [ ] Ajouter au moins un test frontend de build.
- [ ] Tester manuellement le parcours complet avant chaque mise en prod.

## Priorité 9 : déploiement 3 serveurs

- [ ] Préparer le serveur PostgreSQL.
- [ ] Préparer le serveur backend.
- [ ] Préparer le serveur frontend.
- [ ] Copier uniquement les fichiers nécessaires sur chaque serveur.
- [ ] Adapter `POSTGRES_HOST` avec l'IP privée du serveur DB.
- [ ] Adapter la config Nginx frontend pour pointer vers l'IP privée du backend.
- [ ] Vérifier que le backend peut joindre PostgreSQL.
- [ ] Vérifier que Django peut lancer les migrations.
- [ ] Vérifier que Celery peut joindre Redis.
- [ ] Vérifier que le frontend peut joindre le backend via `/api/`.
- [ ] Vérifier que le navigateur ne contacte jamais directement la DB ou Redis.

## Priorité 10 : documentation

- [ ] Compléter `README_DEPLOY_3_SERVEURS.md` avec les vraies IP/DNS de production.
- [ ] Documenter comment mettre à jour le backend.
- [ ] Documenter comment mettre à jour le frontend.
- [ ] Documenter comment restaurer PostgreSQL.
- [ ] Documenter comment vérifier les logs.
- [ ] Documenter comment redémarrer Celery.
- [ ] Documenter la procédure de rollback.
