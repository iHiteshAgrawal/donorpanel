"""Builds both images and pushes them to ECR. Idempotent: rerun to ship a change."""
import base64
import subprocess
import sys

import boto3
from botocore.exceptions import ClientError

from deploy.settings import LAMBDA_REPO, REGION, RUNTIME_REPO, repo_uri

ecr = boto3.client("ecr", region_name=REGION)

IMAGES = [
    (RUNTIME_REPO, "Dockerfile.runtime"),
    (LAMBDA_REPO, "Dockerfile.lambda"),
]


def run(*args: str) -> None:
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode:
        print(result.stdout[-2000:], result.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"failed: {' '.join(args[:3])}")


def ensure_repo(name: str) -> None:
    try:
        ecr.create_repository(repositoryName=name,
                              imageScanningConfiguration={"scanOnPush": True},
                              tags=[{"Key": "project", "Value": "donorpanel"}])
        print(f"  created repo {name}")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "RepositoryAlreadyExistsException":
            raise
        print(f"  repo {name} exists")


def login() -> None:
    token = ecr.get_authorization_token()["authorizationData"][0]
    user, password = base64.b64decode(token["authorizationToken"]).decode().split(":", 1)
    run("docker", "login", "--username", user, "--password", password,
        token["proxyEndpoint"])


def main() -> None:
    for name, _ in IMAGES:
        ensure_repo(name)
    login()
    for name, dockerfile in IMAGES:
        uri = f"{repo_uri(name)}:latest"
        print(f"  building {dockerfile}")
        # Both targets are arm64: Runtime requires it, and Lambda runs Graviton.
        run("docker", "build", "--platform", "linux/arm64", "-f", dockerfile,
            "-t", uri, ".")
        print(f"  pushing  {uri}")
        run("docker", "push", uri)
    print("done")


if __name__ == "__main__":
    main()
