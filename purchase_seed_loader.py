from pathlib import Path
from purchase_data_pipeline import import_asking_csv
def load_verified_seed():
    p=Path(__file__).with_name('verified_purchase_seed_2026.csv')
    return import_asking_csv(p.read_text(encoding='utf-8'),'Magazine des Notaires Gironde / SCP Chambarière et Figerou','NOTARY_LISTING')
