# Kubernetes NGINX Deployment

A complete Kubernetes deployment configuration for running NGINX web servers using YAML manifests. This repository contains production-ready configurations with best practices for resource manageme[...]

## 📋 Table of Contents

- [Overview](#overview)
- [Repository Structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Installation & Deployment](#installation--deployment)
- [Configuration Files](#configuration-files)
- [Resource Specifications](#resource-specifications)
- [Usage Examples](#usage-examples)
- [Example: Using GREETING in a Python script](#example-using-greeting-in-a-python-script)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Overview

This project provides a complete setup for deploying NGINX on Kubernetes clusters. It includes:

- **Namespace Management**: Isolated namespace for custom deployments (`my-web-namespace`)
- **Deployment Configuration**: Production-ready NGINX deployment with 3 replicas
- **Resource Management**: CPU and memory requests/limits for proper resource allocation
- **Volume Management**: Persistent storage configuration with PersistentVolumeClaim
- **Environment Configuration**: Environment variables and port configuration

## Repository Structure

```
.
├── README.md                    # This file
├── LICENSE                      # Apache License 2.0
├── k8s-namespace.yaml          # Kubernetes Namespace resource
└── k8s-deployement.yaml        # NGINX Deployment configuration
```

## Prerequisites

Before deploying, ensure you have:

- A running Kubernetes cluster (v1.20+)
- `kubectl` command-line tool configured to access your cluster
- Appropriate permissions to create namespaces and deployments
- A PersistentVolume and StorageClass available (for PersistentVolumeClaim)

## Installation & Deployment

### Step 1: Create the Namespace

```bash
kubectl apply -f k8s-namespace.yaml
```

Verify the namespace was created:
```bash
kubectl get namespaces
```

### Step 2: Deploy NGINX

```bash
kubectl apply -f k8s-deployement.yaml
```

Verify the deployment:
```bash
kubectl get deployments -n my-web-namespace
kubectl get pods -n my-web-namespace
```

### Step 3: Check Pod Status

```bash
# View all pods in the namespace
kubectl get pods -n my-web-namespace -o wide

# View detailed pod information
kubectl describe pod <pod-name> -n my-web-namespace

# View pod logs
kubectl logs <pod-name> -n my-web-namespace
```

## Configuration Files

### k8s-namespace.yaml

Creates an isolated Kubernetes namespace for organizational purposes.

**Key Components:**
- **apiVersion**: v1 (Core Kubernetes API)
- **kind**: Namespace
- **name**: `my-web-namespace`
- **labels**: Environment tagging (production)

### k8s-deployement.yaml

Main deployment configuration for NGINX with full production specifications.

**Key Components:**

#### Metadata
- **name**: `my-web-app`
- **namespace**: `my-web-namespace` (deploys into custom namespace)
- **labels**: `app: web`, `environment: prod` (for resource organization)

#### Deployment Spec
- **replicas**: 3 (three NGINX pod instances for high availability)
- **selector**: Matches pods with `app: web` label

#### Pod Template
- **Image**: `nginx:1.25` (specific stable NGINX version)
- **Container Port**: 80 (HTTP traffic)
- **Protocol**: TCP

#### Resource Management
```yaml
Resources:
  Requests:           # Minimum guaranteed resources
    CPU: 250m         # 0.25 CPU cores
    Memory: 256Mi     # 256 Mebibytes

  Limits:             # Maximum allowed resources
    CPU: 500m         # 0.5 CPU cores
    Memory: 512Mi     # 512 Mebibytes
```

#### Environment Variables
- `APP_ENV`: Set to `production`

#### Storage
- **Volume Name**: `app-data`
- **Mount Path**: `/var/www/html`
- **Type**: PersistentVolumeClaim (`my-web-pvc`)
- **Access**: Read-Write enabled

## Resource Specifications

### CPU & Memory

The deployment uses resource requests and limits to ensure proper scheduling and cluster stability:

| Resource | Request | Limit | Purpose |
|----------|---------|-------|---------|
| CPU | 250m | 500m | Guarantees 250m, allows up to 500m for spikes |
| Memory | 256Mi | 512Mi | Guarantees 256Mi, limits to 512Mi to prevent OOM |

### Scaling

The deployment creates **3 replicas** of the NGINX container by default. To scale:

```bash
# Scale to 5 replicas
kubectl scale deployment my-web-app -n my-web-namespace --replicas=5

# Scale down to 1 replica
kubectl scale deployment my-web-app -n my-web-namespace -–replicas=1
```

## Usage Examples

### Access NGINX

Create a port-forward to access NGINX locally:
```bash
kubectl port-forward -n my-web-namespace svc/my-web-app 8080:80
```

Then access: `http://localhost:8080`

### Update NGINX Version

Edit the deployment to update the image:
```bash
kubectl set image deployment/my-web-app web-server=nginx:1.26 \
  -n my-web-namespace
```

### View Deployment Status

```bash
# Get deployment summary
kubectl get deployment my-web-app -n my-web-namespace

# Get detailed deployment info
kubectl describe deployment my-web-app -n my-web-namespace

# View deployment rollout history
kubectl rollout history deployment/my-web-app -n my-web-namespace
```

### Edit Deployment

```bash
kubectl edit deployment my-web-app -n my-web-namespace
```

### Delete Deployment

```bash
kubectl delete deployment my-web-app -n my-web-namespace
```

### Delete Namespace

```bash
# Note: Deleting the namespace also deletes all resources within it
kubectl delete namespace my-web-namespace
```

## Example: Using GREETING in a Python script

If you want to run a simple Python script that reads an environment variable named GREETING, you can add a small script to the repository and set the environment variable on your pod or deployment.

1) Create a file named `greet.py` with the following content:

```python
# greet.py
import os
print(os.environ["GREETING"])
```

2) Run locally:

```bash
# Run with an environment variable set
GREETING="Hello from local" python3 greet.py
```

3) Run inside an existing pod (quick test):

```bash
# Copy the script into a running pod and execute it
kubectl cp greet.py <pod-name>:/tmp/greet.py -n my-web-namespace
kubectl exec -it <pod-name> -n my-web-namespace -- python3 /tmp/greet.py
```

Note: The pod must have Python installed for the above to work. The NGINX image does not include Python by default.

4) Set GREETING as an environment variable in your Kubernetes deployment spec (e.g., in `k8s-deployement.yaml`) under the container spec:

```yaml
containers:
  - name: web-server
    image: nginx:1.25
    env:
      - name: GREETING
        value: "Hello from Kubernetes"
```

After applying the change, you can exec into a pod that has Python (or add a sidecar/container that runs Python) to read the variable. Alternatively, set the env var on a debug pod that uses a Python image:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: debug-python
  namespace: my-web-namespace
spec:
  containers:
    - name: python
      image: python:3.11-slim
      command: ["sleep", "infinity"]
      env:
        - name: GREETING
          value: "Hello from Kubernetes"
```

Apply and then run:

```bash
kubectl apply -f debug-python.yaml
kubectl exec -it debug-python -n my-web-namespace -- python3 -c 'import os; print(os.environ["GREETING"])'
```

This README section shows where to place the small Python file (`greet.py`) and how to set/use the GREETING environment variable both locally and in Kubernetes.

## Troubleshooting

### Pods not starting

```bash
# Check pod status and events
kubectl describe pod <pod-name> -n my-web-namespace

# View pod logs
kubectl logs <pod-name> -n my-web-namespace

# Check resource availability
kubectl top nodes
kubectl top pods -n my-web-namespace
```

### PersistentVolumeClaim issues

```bash
# Check PVC status
kubectl get pvc -n my-web-namespace

# Describe PVC for details
kubectl describe pvc my-web-pvc -n my-web-namespace

# List available PersistentVolumes
kubectl get pv
```

### ImagePullBackOff errors

Ensure the NGINX image is available. If using a private registry:
```bash
kubectl create secret docker-registry regcred \
  --docker-server=<registry-url> \
  --docker-username=<username> \
  --docker-password=<password> \
  -n my-web-namespace
```

### Out of Memory (OOM) errors

Increase memory limits in the deployment:
```bash
kubectl set resources deployment my-web-app \
  -n my-web-namespace \
  --limits=memory=1Gi \
  --requests=memory=512Mi
```

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for improvements.

## License

This project is licensed under the **Apache License 2.0** - see the [LICENSE](./LICENSE) file for details.

---

**Keywords**: yaml, kubernetes, deployment, nginx, k8s, container, orchestration
