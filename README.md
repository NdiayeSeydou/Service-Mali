# Services Mali

Monorepo de mise en relation clients/professionnels au Mali. Interface en français, montants en FCFA (XOF entiers).

## Lancement local

1. Copier `.env.example` vers `.env`.
2. Démarrer les dépendances : `docker compose up -d db redis`.
3. Backend : `cd backend`, créer un environnement Python 3.12, installer `pip install -r requirements.txt`, puis `python manage.py migrate`, `python manage.py createsuperuser`, `python manage.py runserver`.
4. Frontend : `cd frontend`, `npm install`, copier `.env.example` en `.env.local`, puis `npm run dev`.
5. Worker et expiration des abonnements : dans `backend/`, lancer `celery -A config worker -l info` et `celery -A config beat -l info`.

Frontend : http://localhost:5173 · API : http://localhost:8000/api/docs/ · Admin : http://localhost:8000/admin/
L’e-mail de réinitialisation s’affiche dans la console Django par défaut.

## Docker Compose complet

`docker compose up --build` lance PostgreSQL, Redis, Django/Gunicorn, Celery worker/beat, Nginx et le frontend. La plateforme est disponible sur http://localhost.

## Vérifications

Depuis `backend/` : `pytest`, `ruff check .`, `python manage.py check`, `python manage.py makemigrations --check --dry-run`.
Depuis `frontend/` : `npm run build`, `npm run lint`.

## API comptes et profils

- `POST /api/auth/register/`: rôles publics `CLIENT` et `PROFESSIONNEL`; un profil pro est créé en attente.
- `POST /api/auth/login/`, `/api/auth/refresh/`: JWT d’accès et de renouvellement.
- `POST /api/auth/password-reset/`, `/api/auth/password-reset/confirm/`: lien e-mail limité dans le temps.
- `GET/PATCH /api/auth/me/`: compte; `GET/PATCH /api/auth/professionals/me/`: bio, métiers, zones, pièce d’identité.
- `POST /api/auth/professionals/me/gallery/`: ajout d’image à la galerie.
- `POST /api/auth/admin/professionals/{id}/verification/`: action `verify` ou `reject`, réservée aux admins.
- `GET /api/auth/professionals/`: professionnels vérifiés, Premium en premier.

## Demandes, devis, messagerie, paiements et abonnements

- `POST/GET /api/requests/` : un client publie et consulte ses demandes; un professionnel consulte les demandes publiées.
- `POST /api/quotes/`, `GET /api/requests/{id}/quotes/`, `POST /api/quotes/{id}/accept/` : devis réservés aux professionnels vérifiés; seul le client propriétaire accepte. L’acceptation est atomique : un seul devis devient `ACCEPTED`, tous les autres passent à `CLOSED` et la demande cesse d’accepter des devis.
- `GET/POST /api/quotes/{id}/messages/` : conversation liée à un devis, accessible uniquement au client propriétaire et au professionnel émetteur; l’envoi est fermé pour les devis clôturés.
- `POST /api/payments/checkout/` avec `request_id`, `provider` (`WAVE` ou `ORANGE_MONEY`), `success_url` et `error_url` crée une session sandbox.
- L’URL de paiement sandbox renvoyée simule une confirmation; seul le traitement serveur signe et traite son webhook. Les webhooks opérateurs sont reçus par `POST /api/payments/webhooks/{provider}/` (`WAVE` ou `ORANGE_MONEY`). Une relecture du statut provider, du montant attendu et de `XOF` précède le crédit séquestre.
- Après le paiement : le professionnel passe la prestation en cours puis la marque terminée; seul le client propriétaire peut la valider. Le serveur libère alors le montant net au compte à payer du professionnel et comptabilise la commission. L’historique des transitions et le ledger sont immuables.
- `GET /api/subscriptions/plans/`, `GET /api/subscriptions/me/`, `POST /api/subscriptions/checkout/` gèrent Premium. Le webhook confirmé active l’abonnement; Celery Beat expire les abonnements chaque jour.

Le mode `PAYMENT_MODE=sandbox` ne contacte aucun opérateur et doit rester le mode local. Les secrets de webhook sont configurés par variables d’environnement; les clés d’API réelles, la conformité opérateur et les callbacks de production restent à configurer avant toute mise en service financière.

Les métiers et zones sont définis depuis l’admin Django. Les documents d’identité sont écrits dans un stockage privé et exclus des réponses API.


## Avis, litiges et notifications

- `POST /api/reviews/` : le client propriétaire peut noter une fois la prestation terminée, validée et ses fonds libérés. `GET /api/reviews/professionals/{id}/` consulte les avis publics.
- `POST /api/requests/{id}/transition/` avec `status: EN_LITIGE` ouvre un litige aux participants. Un enregistrement `EscrowHold` bloque les libérations ordinaires; seul `POST /api/requests/{id}/resolve-dispute/` par un admin arbitre (`RELEASE`, `REFUND` ou `SPLIT`) et écrit les mouvements du ledger.
- Les notifications transactionnelles de nouveau message, devis accepté/clôturé, avis et litige sont placées dans Celery. `NotificationDelivery` journalise chaque destinataire et canal; `NotificationAttempt` garde le résultat et l’erreur de chaque tentative. L’administration Django permet de consulter ces journaux.
- L’e-mail utilise les paramètres SMTP ci-dessus. Pour WhatsApp Cloud API, configurer `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_API_VERSION`, `WHATSAPP_TEMPLATE_NAME` et `WHATSAPP_TEMPLATE_LANGUAGE`. Le modèle Meta configuré doit être approuvé et accepter un paramètre texte dans son corps; sans ces valeurs, l’envoi est journalisé en échec et réessayé par Celery.


## Production et PWA

Le mode local reste dans `docker-compose.yml`. Pour OVH VPS, consulter [`docs/DEPLOYMENT_OVH.md`](docs/DEPLOYMENT_OVH.md), copier `.env.prod.example` vers `.env.prod`, puis lancer `docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build`. Les images de production sont décrites par `backend/Dockerfile.prod` et `frontend/Dockerfile.prod`; Nginx termine TLS, sert les médias publics et les fichiers statiques. `bash scripts/backup.sh` sauvegarde PostgreSQL et les médias. La PWA est compilée par Vite avec son manifest et service worker.
