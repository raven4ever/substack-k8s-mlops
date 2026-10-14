"""Drift monitor, run by a CronJob in the wine namespace.

Compares the data the champion was trained on with the latest data/wine.csv on main.
If Evidently flags dataset drift, it submits a training run on the latest data.
Every check is logged to the MLflow experiment wine-quality-monitoring, with the HTML report.
"""
import os

import dvc.api
from dvc.api import DVCFileSystem
import mlflow
import pandas as pd
from evidently import Report
from evidently.presets import DataDriftPreset
from kfp.client import Client
from mlflow.exceptions import MlflowException

from pipeline import MODEL, REPO, resolve, run_name, submit

KFP_HOST = os.environ.get("KFP_HOST", "http://ml-pipeline.kubeflow:8888")


def data_hash(rev: str) -> str:
    """md5 of data/wine.csv at a Git revision, read from the .dvc pointer (no download)."""
    return DVCFileSystem(REPO, rev=rev).info("data/wine.csv")["md5"]


def features(rev: str) -> pd.DataFrame:
    with dvc.api.open("data/wine.csv", repo=REPO, rev=rev) as f:
        return pd.read_csv(f, sep=";").drop(columns="quality")


def main():
    registry = mlflow.MlflowClient()
    try:
        champion = registry.get_model_version_by_alias(MODEL, "champion")
    except MlflowException:
        print("no champion yet, nothing to compare")
        return
    trained_on = registry.get_run(champion.run_id).data.tags["data_rev"]
    latest = resolve("main")
    if data_hash(latest) == data_hash(trained_on):  # code-only commits do not count
        print(f"champion v{champion.version} is trained on the latest data")
        return

    kfp = Client(host=KFP_HOST)
    if any(r.display_name == run_name(latest) for r in kfp.list_runs(page_size=100).runs or []):
        print(f"a training run for {latest[:7]} already exists")
        return

    snapshot = Report([DataDriftPreset()]).run(reference_data=features(trained_on), current_data=features(latest))
    drift = next(m["value"] for m in snapshot.dict()["metrics"] if m["metric_name"].startswith("DriftedColumnsCount"))
    drifted = drift["share"] >= 0.5  # Evidently's default dataset drift threshold

    mlflow.set_experiment(f"{MODEL}-monitoring")
    with mlflow.start_run(run_name=f"drift-{latest[:7]}", tags={"reference": trained_on, "current": latest}):
        mlflow.log_metrics({"drifted_columns": drift["count"], "drifted_share": drift["share"]})
        snapshot.save_html("drift.html")
        mlflow.log_artifact("drift.html")

    print(f"{drift['count']:.0f} columns drifted ({drift['share']:.0%}) between {trained_on[:7]} and {latest[:7]}")
    if drifted:
        print(f"retraining: run {submit(KFP_HOST, latest)}")


if __name__ == "__main__":
    main()
