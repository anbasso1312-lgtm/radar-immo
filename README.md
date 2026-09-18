# RADAR IMMO V0.3 — données publiques connectées

MVP local de recherche/analyse immobilière Bordeaux-first.

## Ce qui est réellement connecté
- Géocodage Géoplateforme/IGN : adresse -> coordonnées + code INSEE.
- DVF+ / API Données foncières Cerema : présélection de mutations comparables et médiane €/m².
- API Carto Cadastre : parcelle(s) intersectant l'adresse géocodée.
- API Carto / GPU : premier screening zone/prescriptions d'urbanisme.
- Géorisques : connecteur best-effort; la V2 officielle peut nécessiter `GEORISQUES_TOKEN`.
- Off-market manuel : même pipeline d'analyse.

RADAR ne remplit pas artificiellement une donnée absente. Les erreurs d'une source sont affichées sans bloquer les autres sources.

## Installation
Python 3.11+ recommandé.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Puis ouvrir `http://127.0.0.1:8000`.

## Test API
```bash
curl -X POST http://127.0.0.1:8000/api/research \
  -H "Content-Type: application/json" \
  -d '{"address":"10 rue Sainte-Catherine Bordeaux","price":250000,"surface":65,"rooms":3,"monthly_rent":1250,"works":25000}'
```

## Limites importantes
- L'API Données foncières Cerema est encore exposée sur une infrastructure de préproduction : prévoir cache, import local DVF+ et mécanisme de repli avant usage intensif.
- La médiane DVF V0.3 est un **screening**, pas un avis de valeur : la V0.4 ajoutera distance, typologie exacte, récence, étage/état quand disponibles, outliers et pondérations.
- Une zone GPU détectée n'est jamais assimilée à un droit à construire ou à une autorisation.
- Aucun portail d'annonces n'est aspiré sans mode d'accès autorisé.


## V0.4 — secrets et enrichissement

1. Copier `.env.example` vers `.env`.
2. Coller le jeton Géorisques dans `GEORISQUES_API_TOKEN`. Ne jamais l'envoyer dans le chat ni le committer.
3. Exporter les variables avant lancement, par exemple `set -a; source .env; set +a` puis démarrer Uvicorn.

V0.4 ajoute des connecteurs BDNB Open et DPE ADEME ainsi qu'un connecteur Géorisques V2 à jeton. Les correspondances bâtiment/DPE sont des candidats avec niveau d'identité à confirmer : RADAR ne transforme pas un rapprochement en certitude.
