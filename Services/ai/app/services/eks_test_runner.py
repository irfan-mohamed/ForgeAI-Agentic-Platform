"""Run a committed repository snapshot in a restricted Kubernetes Job."""

import base64
import re
import ssl
import time
import uuid
from pathlib import Path

import httpx

_SERVICE_ACCOUNT = Path("/var/run/secrets/kubernetes.io/serviceaccount")
MAX_ARCHIVE_BYTES = 700 * 1024
JOB_TIMEOUT = 300


class RunnerError(RuntimeError):
    """The sandbox could not produce a test result."""


def _job(name: str, image: str) -> dict:
    if not re.fullmatch(r"[^\s]+@sha256:[a-f0-9]{64}", image):
        raise RunnerError("The EKS test profile must use an image pinned by digest.")
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name},
        "spec": {
            "activeDeadlineSeconds": JOB_TIMEOUT,
            "backoffLimit": 0,
            "ttlSecondsAfterFinished": 300,
            "template": {
                "spec": {
                    "restartPolicy": "Never",
                    "automountServiceAccountToken": False,
                    "enableServiceLinks": False,
                    "hostAliases": [{"ip": "127.0.0.1", "hostnames": ["postgres"]}],
                    "securityContext": {
                        "runAsNonRoot": True,
                        "runAsUser": 10001,
                        "runAsGroup": 10001,
                        "fsGroup": 10001,
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "containers": [{
                        "name": "tests",
                        "image": image,
                        "securityContext": {
                            "allowPrivilegeEscalation": False,
                            "readOnlyRootFilesystem": True,
                            "capabilities": {"drop": ["ALL"]},
                        },
                        "resources": {
                            "requests": {"cpu": "250m", "memory": "384Mi", "ephemeral-storage": "128Mi"},
                            "limits": {"cpu": "1", "memory": "1Gi", "ephemeral-storage": "768Mi"},
                        },
                        "volumeMounts": [
                            {"name": "source", "mountPath": "/forgeai-input", "readOnly": True},
                            {"name": "scratch", "mountPath": "/tmp"},
                        ],
                    }],
                    "volumes": [
                        {"name": "source", "secret": {"secretName": name}},
                        {"name": "scratch", "emptyDir": {"sizeLimit": "700Mi"}},
                    ],
                },
            },
        },
    }


def run_archive(namespace: str, image: str, archive: bytes, log) -> tuple[int, str]:
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", namespace):
        raise RunnerError("The EKS test namespace is invalid.")
    if not archive or len(archive) > MAX_ARCHIVE_BYTES:
        raise RunnerError("The compressed repository snapshot exceeds the 700 KiB runner limit.")
    name = f"forgeai-tests-{uuid.uuid4().hex[:16]}"
    job = _job(name, image)
    try:
        token = (_SERVICE_ACCOUNT / "token").read_text(encoding="utf-8").strip()
        tls = ssl.create_default_context(cafile=str(_SERVICE_ACCOUNT / "ca.crt"))
    except OSError as exc:
        raise RunnerError("The AI pod has no Kubernetes service-account credentials.") from exc
    jobs = f"/apis/batch/v1/namespaces/{namespace}/jobs"
    core = f"/api/v1/namespaces/{namespace}"
    with httpx.Client(
        base_url="https://kubernetes.default.svc", verify=tls, trust_env=False,
        headers={"Authorization": f"Bearer {token}"}, timeout=15,
    ) as client:
        created = False
        try:
            response = client.post(jobs, json=job)
            response.raise_for_status()
            created = True
            owner = response.json()["metadata"]
            response = client.post(f"{core}/secrets", json={
                "apiVersion": "v1", "kind": "Secret", "type": "Opaque", "immutable": True,
                "metadata": {
                    "name": name,
                    "ownerReferences": [{
                        "apiVersion": "batch/v1", "kind": "Job", "name": name, "uid": owner["uid"],
                    }],
                },
                "data": {"source.tar.gz": base64.b64encode(archive).decode("ascii")},
            })
            response.raise_for_status()
            log(f"[ForgeAI] EKS test Job {name} started")
            deadline = time.monotonic() + JOB_TIMEOUT + 30
            while time.monotonic() < deadline:
                response = client.get(f"{jobs}/{name}")
                response.raise_for_status()
                conditions = response.json().get("status", {}).get("conditions", [])
                terminal = next((item["type"] for item in conditions
                                 if item["status"] == "True" and item["type"] in {"Complete", "Failed"}), None)
                if terminal:
                    break
                time.sleep(3)
            else:
                raise RunnerError("The EKS test Job timed out.")
            response = client.get(f"{core}/pods", params={"labelSelector": f"batch.kubernetes.io/job-name={name}"})
            response.raise_for_status()
            for pod in response.json()["items"]:
                for container in pod.get("status", {}).get("containerStatuses", []):
                    result = container.get("state", {}).get("terminated")
                    if container["name"] == "tests" and result:
                        logs = client.get(f"{core}/pods/{pod['metadata']['name']}/log",
                                          params={"container": "tests", "limitBytes": 12000})
                        logs.raise_for_status()
                        exit_code = result["exitCode"]
                        if terminal == "Failed" and exit_code == 0:
                            exit_code = 1
                        return exit_code, logs.text
            raise RunnerError("The EKS Job ended before its test container could run.")
        except httpx.HTTPStatusError as exc:
            raise RunnerError(f"Kubernetes rejected the test runner request (HTTP {exc.response.status_code}).") from exc
        except httpx.RequestError as exc:
            raise RunnerError("The EKS runner lost contact with the Kubernetes API.") from exc
        finally:
            if created:
                try:
                    response = client.delete(f"{jobs}/{name}", params={"propagationPolicy": "Background"})
                    if response.status_code not in {200, 202, 404}:
                        log(f"[ForgeAI] Job cleanup deferred to TTL (HTTP {response.status_code})")
                except httpx.RequestError:
                    log("[ForgeAI] Job cleanup deferred to TTL")
