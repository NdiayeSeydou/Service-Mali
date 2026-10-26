# Décisions produit et techniques

- Les inscriptions publiques acceptent CLIENT et PROFESSIONNEL uniquement; le rôle ADMIN est attribué par l’administration.
- Chaque professionnel reçoit un profil EN_ATTENTE. Seuls les profils vérifiés sont publiés et peuvent soumettre un devis.
- La demande de réinitialisation renvoie la même réponse qu’un compte existe ou non afin de limiter l’énumération.
- Les pièces d’identité sont privées, exclues des réponses et limitées à 8 Mo en JPEG, PNG ou PDF.
- Les métiers et zones sont administrés dans Django Admin; galerie et pièce d’identité sont séparées.
- Les paiements restent en mode sandbox par défaut. Les providers Wave et Orange Money n’appellent aucun service financier réel dans ce jalon.
- Le webhook Wave utilise `Wave-Signature` avec HMAC-SHA256 sur `timestamp + corps brut` et une fenêtre anti-rejeu de 5 minutes (30 secondes de tolérance future), suivant la documentation Wave. Le webhook Orange sandbox utilise un HMAC local du corps brut; ce mécanisme simulé ne prétend pas remplacer le protocole de production d’Orange.
- Un webhook signé ne suffit pas à payer : le serveur relit d’abord l’état et le montant de la session provider sandbox, puis vérifie XOF et le montant attendu avant de créditer le séquestre. Les événements et écritures comptables sont idempotents.
- La commission par défaut est 15 %, réglable dans Django Admin en points de base. Calcul entier XOF, arrondi à l’inférieur. À la validation client, le séquestre crédite la plateforme et le compte à payer au professionnel; le transfert externe au professionnel reste manuel.
- La formule Premium par défaut est de 5 000 XOF pour 30 jours, éditable dans Django Admin. L’accès expire selon `expires_at`; Celery Beat met également à jour quotidiennement les statuts échus.
- Une demande appartient au client qui l’a publiée; les professionnels ne voient que les demandes publiées.
- Seuls les professionnels vérifiés peuvent proposer un devis. Un client ne peut accepter qu’un devis de sa demande; l’opération transactionnelle accepte ce devis, clôt tous les autres et ferme la demande aux nouvelles propositions.
- Une conversation est liée à un devis et réservée au client propriétaire et au professionnel émetteur. Les nouveaux messages sont bloqués quand le devis est rejeté ou clôturé automatiquement.

- Un avis est unique par demande et ne peut être publié par le client propriétaire qu’après la libération des fonds; cela matérialise la validation client dans le workflow existant.
- Un litige crée un gel explicite sur le paiement séquestré. La transition générique ne peut pas clore un litige : l’arbitrage admin doit régler les écritures et lever le gel atomiquement.
- E-mails et WhatsApp sont envoyés par les tâches Celery après commit. Chaque canal garde un journal de livraison et un journal distinct par tentative; les échecs sont réessayés jusqu’à quatre tentatives.
- WhatsApp utilise un modèle transactionnel approuvé configurable de la Cloud API Meta; les secrets et modèle restent à fournir par l’exploitant.
