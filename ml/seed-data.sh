#!/usr/bin/env bash
# Fill a fresh SeaweedFS with both data versions that Git points to (tags data-v1 and data-v2).
# The files are rebuilt from the UCI download, so their hashes match the committed .dvc pointers.
set -euo pipefail
cd "$(dirname "$0")/.."

# Talk to SeaweedFS through the ingress, with the platform's credentials.
dvc remote modify --local storage endpointurl http://s3.localhost:8080
secret() { kubectl -n seaweedfs get secret seaweedfs-s3-config -o jsonpath="{.data.$1}" | base64 -d; }
export AWS_ACCESS_KEY_ID="$(secret AWS_ACCESS_KEY_ID)" AWS_SECRET_ACCESS_KEY="$(secret AWS_SECRET_ACCESS_KEY)"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
curl -sSfL -o "$tmp/wine.zip" https://archive.ics.uci.edu/static/public/186/wine+quality.zip
unzip -q -o "$tmp/wine.zip" -d "$tmp"

cp "$tmp/winequality-red.csv" data/wine.csv                    # v1: 1,599 red wines
dvc add -q data/wine.csv
tail -n +2 "$tmp/winequality-white.csv" >> data/wine.csv       # v2: plus 4,898 white wines
dvc add -q data/wine.csv
git checkout -- data/wine.csv.dvc                              # keep the committed pointer
dvc checkout -q data/wine.csv

dvc push --all-tags
