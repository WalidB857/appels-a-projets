from __future__ import annotations
import pandas as pd

from appels_a_projets.connectors.iledefrance_opendata import (
    IdfOpenDataConnector,
    IdfOpenDataConfig,
)

def main():
    # On limite volontairement pour inspection
    cfg = IdfOpenDataConfig(max_records=20)
    conn = IdfOpenDataConnector(cfg)

    items = conn.fetch_as_items()

    # Aplatir pour DataFrame
    rows = []
    for it in items:
        fields = it.get("fields", {}).copy()

        # métadonnées utiles
        fields["_source_item_id"] = it.get("source_item_id")
        fields["_record_timestamp"] = it.get("timestamp")
        fields["_source_url"] = it.get("source_url")

        rows.append(fields)

    df = pd.DataFrame(rows)

    print("Shape :", df.shape)
    print("\nColonnes :")
    print(sorted(df.columns))

    print("\nAperçu :")
    print(df.head(5))

    # Optionnel : afficher les valeurs uniques de certains champs
    if "id_theme" in df.columns:
        print("\nValeurs id_theme :")
        print(df["id_theme"].dropna().unique()[:20])

    if "id_publics" in df.columns:
        print("\nValeurs id_publics :")
        print(df["id_publics"].dropna().unique()[:20])


if __name__ == "__main__":
    main()
