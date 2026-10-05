import requests
import csv
import json
from datetime import datetime, timezone


url = "https://query.wikidata.org/sparql"

headers = {
    "User-Agent": "mkr1/1.0"
}


def run_query(query_file, output_file):

    with open(query_file, encoding="utf-8") as f:
        query = f.read()

    response = requests.get(
        url,
        params={
            "query": query,
            "format": "json"
        },
        headers=headers
    )

    response.raise_for_status()

    result = response.json()

    columns = result["head"]["vars"]
    rows = result["results"]["bindings"]

    with open(output_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)

        writer.writerow(columns)

        for row in rows:
            values = []

            for column in columns:
                if column in row:
                    values.append(row[column]["value"])
                else:
                    values.append("")

            writer.writerow(values)

    print(output_file, "-", len(rows), "рядків")


run_query("q1.rq", "q1.csv")
run_query("q2.rq", "q2.csv")
run_query("q3.rq", "q3.csv")


meta = {
    "retrieved_at": datetime.now(timezone.utc).isoformat()
}

with open("meta.json", "w", encoding="utf-8") as f:
    json.dump(meta, f, indent=2)


print("Готово")