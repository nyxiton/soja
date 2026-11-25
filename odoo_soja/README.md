# Odoo SOJA

Stack Odoo local pour gérer les mêmes objets métier que l'application Django/Angular :

- producteurs et identité
- parcelles et points GPS
- semence et récolte
- stock coopérative
- traitement usine
- dossier bancaire
- partage et services

## Lancer

Depuis la racine du projet :

```bash
docker compose up -d
```

Ouvrir ensuite :

```text
http://localhost:8069/
```

La base `odoo_soja` est initialisee avec le module `SOJA Management`.

Interface SOJA avec le design du frontend :

```text
http://localhost:8069/soja
```

Connexion locale :

```text
Login : admin
Mot de passe : admin
```

## Ports

```text
Odoo : http://localhost:8069
PostgreSQL Odoo : localhost:5434
```

## Identifiants techniques locaux

```text
Mot de passe master Odoo : admin
PostgreSQL : odoo / odoo
```
