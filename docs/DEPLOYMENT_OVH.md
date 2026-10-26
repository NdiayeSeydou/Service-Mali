# Déploiement sur un VPS OVHcloud

Ce guide cible un **VPS OVHcloud sous Ubuntu 24.04 LTS** avec Docker Compose. Il ne vise pas l’hébergement mutualisé. OVHcloud demande un accès SSH administrateur pour déployer une application Docker sur VPS; le guide officiel GitHub Actions décrit également ce flux de déploiement ([documentation OVHcloud](https://help.ovhcloud.com/csm/en-vps-deploy-website-github-actions?id=kb_article_view&sysparm_article=KB0066184)).

## 1. Préparer le VPS et le domaine

1. Créer un VPS Linux dans l’espace client OVHcloud et noter son IPv4 publique.
2. Dans la zone DNS active du domaine, créer un enregistrement `A` à la racine vers cette IPv4. Si `www` est utilisé, ajouter un `CNAME` vers le domaine principal. La documentation OVHcloud rappelle que la propagation peut prendre plusieurs heures ([configuration DNS](https://help.ovhcloud.com/csm/en-gb-documentation-web-cloud-domains-dns-configuration?id=kb_browse_cat&kb_category=3733f35841f8fa104a4e42ace3ea4ea3&kb_id=e17b4f25551974502d4c6e78b7421955)).
3. Se connecter en SSH avec le compte administrateur initial, créer un compte `deploy` avec accès `sudo`, installer les mises à jour, puis désactiver la connexion SSH directe par mot de passe après avoir confirmé que la clé fonctionne.
4. Autoriser les ports TCP 22 (SSH), 80 (HTTP/ACME) et 443 (HTTPS) dans le pare-feu OVHcloud et le pare-feu local du VPS. N’exposer ni PostgreSQL ni Redis sur Internet.
5. Installer Docker Engine et le plugin Docker Compose depuis les dépôts officiels adaptés à Ubuntu.

## 2. Installer l’application

```bash
sudo mkdir -p /opt/services-mali
sudo chown deploy:deploy /opt/services-mali
cd /opt/services-mali
git clone <URL_DU_DEPOT> .
cp .env.prod.example .env.prod
chmod 600 .env.prod
```

Éditer `.env.prod` : choisir le domaine réel, produire un `DJANGO_SECRET_KEY` aléatoire, un mot de passe Postgres long et des secrets de webhooks distincts. Configurer SMTP et, si utilisé, le jeton WhatsApp et un modèle approuvé. Ne jamais committer `.env.prod`.

Les paiements Wave et Orange Money de cette version restent en sandbox. L’environnement de production doit donc conserver `PAYMENT_MODE=sandbox` jusqu’à l’intégration et la validation des API de paiement réelles.

## 3. Obtenir le certificat TLS

Avant le premier démarrage de Nginx, installer Certbot sur le VPS et demander le certificat en mode standalone. Le DNS doit déjà pointer vers ce serveur et le port 80 doit être accessible.

```bash
sudo apt update
sudo apt install -y certbot
sudo certbot certonly --standalone -d services.example.com
```

Remplacer le domaine exemple par celui de `.env.prod`. Vérifier les fichiers `/etc/letsencrypt/live/<domaine>/fullchain.pem` et `privkey.pem`; le conteneur Nginx les montera en lecture seule.

## 4. Démarrer et contrôler la production

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml config
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f backend nginx
```

Le démarrage applique les migrations et collecte les fichiers statiques avant Gunicorn. Vérifier `https://<domaine>/`, `https://<domaine>/api/docs/` et l’administration Django. Créer ensuite le compte superutilisateur :

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml exec backend python manage.py createsuperuser
```

## 5. Sauvegardes et restauration

La sauvegarde inclut PostgreSQL au format custom, les médias publics et pièces d’identité privées, les sommes SHA-256 et conserve 14 jours localement. Ajouter une tâche cron quotidienne en tant que `deploy` :

```cron
15 2 * * * cd /opt/services-mali && bash scripts/backup.sh >> /var/log/services-mali-backup.log 2>&1
```

Copier régulièrement `backups/` vers un stockage indépendant du VPS; les sauvegardes laissées uniquement sur le même serveur ne couvrent pas la perte de celui-ci. Pour tester une restauration, consulter d’abord les sommes de contrôle, puis arrêter backend/Celery, restaurer le dump avec `pg_restore --clean --if-exists` dans la base prévue et ré-extraire les archives dans `/app/media` et `/app/private_uploads`. Faire une répétition sur une base temporaire avant toute restauration de production.

## 6. Déploiement via GitHub Actions

Le workflow **CI** vérifie backend et frontend sur push et pull request. Le workflow **Deploy OVH VPS** est manuel (`workflow_dispatch`) et lance les vérifications avant SSH. Définir dans GitHub :

- Secrets `OVH_HOST`, `OVH_USER`, `OVH_SSH_KEY` et `OVH_KNOWN_HOSTS`.
- Variable `OVH_APP_PATH`, par exemple `/opt/services-mali`.

Le compte `deploy` doit avoir un accès Git en lecture au dépôt (clé de déploiement GitHub si le dépôt est privé). La clé SSH pour Actions doit être limitée au compte `deploy`; `OVH_KNOWN_HOSTS` doit contenir l’empreinte SSH du serveur vérifiée hors bande. Le workflow sauvegarde d’abord, avance la branche `main` et reconstruit Compose. La première installation reste manuelle afin de configurer `.env.prod`, DNS et TLS.

## Exploitation

- Contrôler `docker compose ... ps`, les logs, l’espace disque et l’état des sauvegardes.
- Renouveler le certificat avec Certbot; en mode standalone, arrêter brièvement le service Nginx avant `certbot renew`, puis relancer le stack.
- Mettre à jour les images et dépendances régulièrement, tester la restauration, et garder les secrets hors du dépôt.
- Les certificats sont terminés par Nginx; les cookies sécurisés, l’en-tête proxy HTTPS, HSTS et la redirection TLS sont activés par la configuration de production.
