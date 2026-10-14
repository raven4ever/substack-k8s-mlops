"""Send wines from a CSV to the served model until stopped. Feeds the Grafana dashboard.

    python ml/traffic.py data/wine.csv
"""
import csv
import json
import random
import sys
import time
import urllib.request

URL = "http://wine-quality-wine.localhost:8080/v1/models/wine-quality:predict"

with open(sys.argv[1]) as f:
    rows = [[float(v) for v in row[:-1]] for row in list(csv.reader(f, delimiter=";"))[1:]]  # drop header and quality

while True:
    batch = random.sample(rows, random.randint(1, 5))
    request = urllib.request.Request(URL, json.dumps({"instances": batch}).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            print([round(p, 2) for p in json.load(response)["predictions"]])
    except OSError as e:
        print(f"error: {e}")
    time.sleep(0.2)
