import argparse
import csv
import json
import re
from datetime import datetime
from decimal import Decimal
from collections import Counter

from rdflib import Graph, Namespace, Literal, RDF, RDFS, XSD


EX = Namespace("http://example.org/mkr/")


def make_name(text):
    return text.strip().replace(" ", "_")


def fix_date(date):
    date = date.strip()

    if "." in date:
        date = datetime.strptime(date, "%d.%m.%Y")

    else:
        date = datetime.strptime(date, "%Y-%m-%d")

    return date.strftime("%Y-%m-%d")


parser = argparse.ArgumentParser()
parser.add_argument("csv_file")
parser.add_argument("params_file")
parser.add_argument("output_file")
args = parser.parse_args()


with open(args.params_file, encoding="utf-8") as f:
    params = json.load(f)

budget_limit = Decimal(str(params["budget_threshold_eur"]))
long_limit = int(params["long_flight_min"])


# читаємо csv і одночасно прибираємо дублікати
flights = {}

with open(args.csv_file, encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)

    for row in reader:
        flight_id = row["flight_id"].strip().upper()

        if flight_id not in flights:
            flights[flight_id] = {
                "id": flight_id,
                "airline": row["airline"].strip(),
                "from_city": row["from_city"].strip().title(),
                "from_country": row["from_country"].strip().title(),
                "to_city": row["to_city"].strip().title(),
                "to_country": row["to_country"].strip().title(),
                "date": fix_date(row["dep_date"]),
                "duration": int(row["duration_min"]),
                "price": row["price_eur"].strip(),
                "note": row["note"].strip()
            }


# рахуємо, скільки рейсів вилітає з кожної країни
country_count = Counter()

for flight in flights.values():
    country_count[flight["from_country"]] += 1


g = Graph()

g.bind("ex", EX)
g.bind("rdf", RDF)
g.bind("rdfs", RDFS)
g.bind("xsd", XSD)


# класи
classes = [
    EX.Flight,
    EX.Airline,
    EX.City,
    EX.Country,
    EX.BudgetFlight,
    EX.LongFlight
]

for c in classes:
    g.add((c, RDF.type, RDFS.Class))

g.add((EX.BudgetFlight, RDFS.subClassOf, EX.Flight))
g.add((EX.LongFlight, RDFS.subClassOf, EX.Flight))


# властивості
properties = [
    (EX.operatedBy, EX.Flight, EX.Airline),
    (EX.departsFrom, EX.Flight, EX.City),
    (EX.arrivesAt, EX.Flight, EX.City),
    (EX.locatedIn, EX.City, EX.Country),
    (EX.departureDate, EX.Flight, XSD.date),
    (EX.durationMin, EX.Flight, XSD.integer),
    (EX.priceEur, EX.Flight, XSD.decimal),
    (EX.hasDelayMinutes, EX.Flight, XSD.integer),
    (EX.reportedBy, RDF.Statement, RDFS.Resource),
    (EX.fromBusyCountry, EX.Flight, XSD.boolean)
]

for prop, domain, range_value in properties:
    g.add((prop, RDF.type, RDF.Property))
    g.add((prop, RDFS.domain, domain))
    g.add((prop, RDFS.range, range_value))


for data in flights.values():

    flight = EX["flight/" + make_name(data["id"])]
    airline = EX["airline/" + make_name(data["airline"])]

    from_city = EX["city/" + make_name(data["from_city"])]
    to_city = EX["city/" + make_name(data["to_city"])]

    from_country = EX["country/" + make_name(data["from_country"])]
    to_country = EX["country/" + make_name(data["to_country"])]


    # авіакомпанія
    g.add((airline, RDF.type, EX.Airline))
    g.add((airline, RDFS.label, Literal(data["airline"], lang="en")))


    # міста і країни
    g.add((from_city, RDF.type, EX.City))
    g.add((from_city, RDFS.label, Literal(data["from_city"], lang="en")))

    g.add((to_city, RDF.type, EX.City))
    g.add((to_city, RDFS.label, Literal(data["to_city"], lang="en")))

    g.add((from_country, RDF.type, EX.Country))
    g.add((from_country, RDFS.label, Literal(data["from_country"], lang="en")))

    g.add((to_country, RDF.type, EX.Country))
    g.add((to_country, RDFS.label, Literal(data["to_country"], lang="en")))

    g.add((from_city, EX.locatedIn, from_country))
    g.add((to_city, EX.locatedIn, to_country))


    # дані самого рейсу
    g.add((flight, EX.operatedBy, airline))
    g.add((flight, EX.departsFrom, from_city))
    g.add((flight, EX.arrivesAt, to_city))

    g.add((
        flight,
        EX.departureDate,
        Literal(data["date"], datatype=XSD.date)
    ))

    g.add((
        flight,
        EX.durationMin,
        Literal(data["duration"], datatype=XSD.integer)
    ))


    special_type = False

    if data["price"] != "":
        price = Decimal(data["price"])

        g.add((
            flight,
            EX.priceEur,
            Literal(price, datatype=XSD.decimal)
        ))

        if price <= budget_limit:
            g.add((flight, RDF.type, EX.BudgetFlight))
            special_type = True


    if data["duration"] >= long_limit:
        g.add((flight, RDF.type, EX.LongFlight))
        special_type = True


    if not special_type:
        g.add((flight, RDF.type, EX.Flight))


    if country_count[data["from_country"]] >= 2:
        g.add((
            flight,
            EX.fromBusyCountry,
            Literal(True, datatype=XSD.boolean)
        ))


    # затримка
    if data["note"]:
        match = re.search(r"delay=(\d+);by=([^;]+)", data["note"])

        if match:
            delay = int(match.group(1))
            source_name = match.group(2).strip()

            statement = EX[
                "stmt/" + make_name(data["id"]) + "-delay"
            ]

            source = EX[
                "source/" + make_name(source_name)
            ]

            g.add((statement, RDF.type, RDF.Statement))
            g.add((statement, RDF.subject, flight))
            g.add((statement, RDF.predicate, EX.hasDelayMinutes))

            g.add((
                statement,
                RDF.object,
                Literal(delay, datatype=XSD.integer)
            ))

            g.add((statement, EX.reportedBy, source))


g.serialize(
    destination=args.output_file,
    format="turtle"
)

print("Граф створено:", args.output_file)
print("Кількість рейсів:", len(flights))
print("Кількість тріплів:", len(g))