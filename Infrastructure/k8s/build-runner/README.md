# Feature Planner sandbox

The AI service creates one Kubernetes Job per test attempt in `forgeai-build-sandbox`. It sends a compressed archive of the candidate commit through a short-lived Secret owned by the Job. The test pod has no Kubernetes token, mounts no ForgeAI credentials, and runs as a non-root user with a read-only root filesystem. Job exit status gates PR creation.

## Activation

1. Enforce the sandbox namespace's deny-all NetworkPolicy from the start of pod execution. On Amazon VPC CNI, enable network policy and use strict startup enforcement. Strict mode also applies outside the sandbox, so prepare and verify policies for existing workloads, including CoreDNS, before switching. Verify egress to the API server, instance metadata, and application services is blocked from a sandbox Job.
2. Apply `sandbox.yaml`. Configure the AI Deployment to use `serviceAccountName: forgeai-build-controller` with service-account token mounting.
3. Prepare an administrator-owned runner image for each supported repository and push it to the project registry. For the Python/PostgreSQL profile, copy the approved dependency manifest into a temporary Docker build context alongside `Infrastructure/build-runners/python-postgres/Dockerfile` and `run.sh`. Set `APP_IMPORT` and `HEALTH_PATH` for the application being tested. For Hotel Booking, the defaults are `app.main:app` and `/health`. Set `PYTEST_IGNORE=tests/test_langfuse.py` for that repository's offline profile because the file makes live telemetry calls during collection.
4. Set `BUILD_EKS_RUNNER_NAMESPACE=forgeai-build-sandbox` and set `BUILD_EKS_RUNNER_IMAGES` to a JSON object mapping a GitHub `owner/repository` to its trusted ECR image reference pinned with `@sha256:...`. Leaving the namespace unset keeps the existing local Docker backend.

The first runner supports offline projects, repository snapshots up to 700 KiB compressed, and PostgreSQL on loopback for the provided profile. The repository's tests still need to pass. A build stops before publication if the target branch has moved since the tested checkout. Publishing through the GitHub App requires Contents and Pull requests write permissions on the target repository.
