"""Wine quality training pipeline on Kubeflow Pipelines.

load-data -> validate-data -> train -> promote

promote makes the new model the MLflow `champion` only if it beats the current champion on the
same held-out split, then rolls the KServe InferenceService to it.

Submit from the laptop:
    uv run --with kfp==2.17.0 --with kfp-kubernetes==2.17.0 python ml/pipeline.py --data-rev main
"""
import argparse
import functools
import subprocess
from pathlib import Path

from kfp import dsl, kubernetes
from kfp.client import Client

VERSION = (Path(__file__).parent / "VERSION").read_text().strip()
IMAGE = f"ghcr.io/raven4ever/substack-k8s-mlops/ml:{VERSION}"
REPO = "https://github.com/raven4ever/substack-k8s-mlops"
MLFLOW = "http://mlflow.mlflow:5000"
MODEL = "wine-quality"
NAMESPACE = "wine"  # where the model is served

component = functools.partial(dsl.component, base_image=IMAGE, install_kfp_package=False)


@component
def load_data(repo: str, data_rev: str, data: dsl.Output[dsl.Dataset]):
    """Read data/wine.csv at a Git revision; DVC fetches the content from SeaweedFS."""
    import dvc.api
    import pandas as pd

    with dvc.api.open("data/wine.csv", repo=repo, rev=data_rev) as f:
        pd.read_csv(f, sep=";").to_csv(data.path, index=False)


@component
def validate_data(data: dsl.Input[dsl.Dataset]):
    """Fail the run before training on data that does not look like wine."""
    import pandas as pd

    df = pd.read_csv(data.path)
    expected = {
        "fixed acidity", "volatile acidity", "citric acid", "residual sugar", "chlorides",
        "free sulfur dioxide", "total sulfur dioxide", "density", "pH", "sulphates", "alcohol", "quality",
    }
    problems = []
    if set(df.columns) != expected:
        problems.append(f"unexpected columns: {sorted(set(df.columns) ^ expected)}")
    if df.isna().any().any():
        problems.append("missing values")
    if len(df) < 500:
        problems.append(f"only {len(df)} rows")
    if "quality" in df and not df["quality"].between(0, 10).all():
        problems.append("quality outside 0-10")
    if problems:
        raise ValueError("; ".join(problems))
    print(f"{len(df)} rows OK")


@component
def train(data: dsl.Input[dsl.Dataset], data_rev: str, model_name: str) -> str:
    """Train, log to MLflow and register a new model version. Returns the version."""
    import mlflow
    import pandas as pd
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import root_mean_squared_error
    from sklearn.model_selection import train_test_split

    df = pd.read_csv(data.path)
    x_train, x_test, y_train, y_test = train_test_split(
        df.drop(columns="quality"), df["quality"], test_size=0.2, random_state=42
    )
    mlflow.set_experiment(model_name)
    with mlflow.start_run(tags={"data_rev": data_rev}):
        params = {"n_estimators": 100, "random_state": 42}
        mlflow.log_params(params)
        model = RandomForestRegressor(**params).fit(x_train, y_train)
        mlflow.log_metric("rmse", root_mean_squared_error(y_test, model.predict(x_test)))
        # Plain pickle: KServe's sklearn runtime loads model.pkl straight from the artifact folder.
        info = mlflow.sklearn.log_model(
            model, name="model", registered_model_name=model_name,
            serialization_format="pickle", input_example=x_test.head(3),
        )
    return str(info.registered_model_version)


@component
def promote(data: dsl.Input[dsl.Dataset], version: str, model_name: str, namespace: str):
    """Champion/challenger on the same test split; the winner gets the alias and the traffic."""
    import mlflow
    import pandas as pd
    from kubernetes import client, config
    from mlflow.exceptions import MlflowException
    from sklearn.metrics import root_mean_squared_error
    from sklearn.model_selection import train_test_split

    df = pd.read_csv(data.path)
    _, x_test, _, y_test = train_test_split(
        df.drop(columns="quality"), df["quality"], test_size=0.2, random_state=42
    )

    def rmse(uri):
        return root_mean_squared_error(y_test, mlflow.sklearn.load_model(uri).predict(x_test))

    challenger = rmse(f"models:/{model_name}/{version}")
    try:
        champion = rmse(f"models:/{model_name}@champion")
    except MlflowException:
        champion = float("inf")  # first model ever
    print(f"challenger v{version}: rmse {challenger:.3f}, champion: rmse {champion:.3f}")
    if challenger >= champion:
        print("champion stays")
        return

    registry = mlflow.MlflowClient()
    registry.set_registered_model_alias(model_name, "champion", version)
    model_id = registry.get_model_version(model_name, version).model_id
    # MLflow proxies artifacts: mlflow-artifacts:/<path> lives at s3://mlflow/<path> in SeaweedFS.
    storage_uri = mlflow.get_logged_model(model_id).artifact_location.replace("mlflow-artifacts:", "s3://mlflow")

    isvc = {
        "apiVersion": "serving.kserve.io/v1beta1",
        "kind": "InferenceService",
        "metadata": {"name": model_name, "namespace": namespace, "labels": {"model-version": version}},
        "spec": {"predictor": {
            "serviceAccountName": "wine-model",  # carries the S3 credentials, see apps/wine
            "model": {"modelFormat": {"name": "sklearn"}, "storageUri": storage_uri},
        }},
    }
    config.load_incluster_config()
    api = client.CustomObjectsApi()
    target = ("serving.kserve.io", "v1beta1", namespace, "inferenceservices")
    try:
        api.patch_namespaced_custom_object(*target, model_name, isvc)
    except client.ApiException as e:
        if e.status != 404:
            raise
        api.create_namespaced_custom_object(*target, isvc)
    print(f"v{version} is champion, serving {storage_uri}")


@dsl.pipeline(name=MODEL, description="Train a wine quality model and promote it if it beats the champion.")
def wine_quality(data_rev: str):
    data = load_data(repo=REPO, data_rev=data_rev)
    kubernetes.use_secret_as_env(
        data, secret_name="s3-credentials",  # DVC reads from SeaweedFS
        secret_key_to_env={"AWS_ACCESS_KEY_ID": "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY": "AWS_SECRET_ACCESS_KEY"},
    )
    checked = validate_data(data=data.outputs["data"])
    trained = train(data=data.outputs["data"], data_rev=data_rev, model_name=MODEL).after(checked)
    promoted = promote(data=data.outputs["data"], version=trained.output, model_name=MODEL, namespace=NAMESPACE)
    for task in (trained, promoted):
        task.set_env_variable("MLFLOW_TRACKING_URI", MLFLOW)
        task.set_caching_options(False)  # side effects in MLflow and KServe: never replay from cache


def resolve(rev: str) -> str:
    """Branch or tag -> commit SHA, so every run records exactly which data it saw."""
    out = subprocess.run(["git", "ls-remote", REPO, rev], capture_output=True, text=True, check=True).stdout
    return out.split()[0] if out else rev


def run_name(sha: str) -> str:
    return f"{MODEL}-{sha[:7]}"


def submit(host: str, data_rev: str) -> str:
    sha = resolve(data_rev)
    run = Client(host=host).create_run_from_pipeline_func(
        wine_quality, arguments={"data_rev": sha}, run_name=run_name(sha), experiment_name=MODEL
    )
    return run.run_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-rev", default="main", help="Git branch, tag or commit of data/wine.csv")
    parser.add_argument("--host", default="http://kfp.localhost:8080", help="Kubeflow Pipelines API")
    args = parser.parse_args()
    print(f"run {submit(args.host, args.data_rev)} submitted, see {args.host}")
