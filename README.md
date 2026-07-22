# Kubernetes NGINX Deployment

A complete Kubernetes deployment configuration for running NGINX web servers using YAML manifests. This repository contains production-ready configurations with best practices for resource manageme[...]

## 📋 Table of Contents

- [Overview](#overview)
- [Repository Structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Installation & Deployment](#installation--deployment)
- [Configuration Files](#configuration-files)
- [YAML Structure of all files](#yaml-structure-of-all-files)
- [K8s Job](#k8s-job)
- [K8s CronJob](#k8s-cronjob)
- [concurrencyPolicy Options](#concurrencypolicy-options)
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
- **Job & CronJob Automation**: One-time and scheduled job execution examples

## Repository Structure

```
.
├── README.md                    # This file
├── LICENSE                      # Apache License 2.0
├── k8s-namespace.yaml          # Kubernetes Namespace resource
├── k8s-deployement.yaml        # NGINX Deployment configuration
├── k8s-job.yaml                # Kubernetes Job resource
└── k8s-cronjob.yaml            # Kubernetes CronJob resource
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

### Step 3: Deploy Jobs (Optional)

```bash
# Deploy a one-time job
kubectl apply -f k8s-job.yaml

# Deploy a scheduled cronjob
kubectl apply -f k8s-cronjob.yaml
```

### Step 4: Check Pod Status

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

## YAML Structure of all files

Below are concise skeletons and explanations of the YAML manifests included in this repository. Use these as a quick reference when you need to understand or extend the manifests.

### 1) k8s-namespace.yaml

Purpose: create an isolated namespace for the deployment.

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: my-web-namespace
  labels:
    environment: production
  # optional: annotations
```

Top-level fields:
- apiVersion
- kind
- metadata.name
- metadata.labels / metadata.annotations

---

### 2) k8s-deployement.yaml

Purpose: define the Deployment for the NGINX application.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-web-app
  namespace: my-web-namespace
  labels:
    app: web
    environment: prod
spec:
  replicas: 3
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
        - name: web-server
          image: nginx:1.25
          ports:
            - containerPort: 80
              protocol: TCP
          env:
            - name: APP_ENV
              value: "production"
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
          volumeMounts:
            - name: app-data
              mountPath: /var/www/html
      volumes:
        - name: app-data
          persistentVolumeClaim:
            claimName: my-web-pvc
```

Top-level fields to look for:
- apiVersion, kind, metadata
- spec.replicas, spec.selector, spec.template
- spec.template.spec.containers[] and their image/ports/env/resources/volumeMounts
- spec.template.spec.volumes[] (PersistentVolumeClaim or emptyDir)

---

### 3) k8s-job.yaml

Purpose: run a one-time job or batch task.

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: backup-job
  namespace: my-web-namespace
spec:
  backoffLimit: 3
  template:
    spec:
      containers:
        - name: backup
          image: backup-utility:1.0
          command: ["./backup.sh"]
      restartPolicy: Never
```

Key fields:
- spec.template.spec.containers[] (image, command, args)
- restartPolicy
- backoffLimit

---

### 4) k8s-cronjob.yaml

Purpose: schedule Jobs on a repeating cadence (cron syntax).

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: backup-cronjob
  namespace: my-web-namespace
spec:
  schedule: "0 2 * * *"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 1
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: backup
              image: backup-utility:1.0
              command: ["./backup.sh"]
          restartPolicy: OnFailure
      backoffLimit: 3
```

Key fields:
- spec.schedule (cron string)
- spec.concurrencyPolicy (Allow / Forbid / Replace)
- spec.jobTemplate.spec.template.spec.containers[]
- restartPolicy, backoffLimit, history limits

---

### 5) PersistentVolumeClaim (used by deployment)

Purpose: declare the claim a pod will mount. Example skeleton below — actual storage depends on cluster/storage class.

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-web-pvc
  namespace: my-web-namespace
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
  storageClassName: standard  # optional, depends on cluster
```

Key fields:
- spec.accessModes
- spec.resources.requests.storage
- spec.storageClassName (optional)

---

Notes & tips:
- Use metadata.labels consistently to enable selectors, monitoring, and RBAC scoping.
- Keep container images pinned to a specific tag for reproducible deployments (e.g., `nginx:1.25`).
- Add readinessProbe and livenessProbe in production deployments to improve resilience.
- Define resource requests and limits to prevent scheduling and OOM issues.

## K8s Job

A Kubernetes Job creates one or more pods and ensures that a specified number of them successfully terminate. Jobs are useful for running one-time tasks, batch processing, or scheduled maintenanc[...]

**Key Characteristics:**
- Runs one or more pods to completion
- Automatically retries failed pods (configurable)
- Suitable for batch processing, one-time operations, and data processing tasks
- Can run in parallel or sequentially

**Use Cases:**
- Database backups
- Data migrations
- Report generation
- Batch data processing
- One-time maintenance tasks

**Example Job Configuration:**

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: backup-job
  namespace: my-web-namespace
spec:
  template:
    spec:
      containers:
      - name: backup
        image: backup-utility:1.0
        command: ["./backup.sh"]
      restartPolicy: Never
  backoffLimit: 3  # Number of retries before marking job as failed
```

**Useful Commands:**

```bash
# Create a job
kubectl apply -f k8s-job.yaml

# List jobs
kubectl get jobs -n my-web-namespace

# Get detailed job information
kubectl describe job backup-job -n my-web-namespace

# View job logs
kubectl logs job/backup-job -n my-web-namespace

# Delete a job
kubectl delete job backup-job -n my-web-namespace
```

## K8s CronJob

A Kubernetes CronJob creates Jobs on a repeating schedule, similar to Linux `cron`. It uses the standard cron format for scheduling.

**Key Characteristics:**
- Runs jobs on a scheduled basis
- Uses cron syntax for scheduling (minute, hour, day, month, day-of-week)
- Automatically creates Job objects according to the schedule
- Manages job history and cleanup
- Supports timezone configuration

**Use Cases:**
- Daily/hourly database backups
- Scheduled data cleanup
- Periodic health checks
- Report generation
- Regular maintenance tasks

**Cron Schedule Format:**
```
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of week (0 - 6) (Sunday to Saturday)
│ │ │ │ │
│ │ │ │ │
* * * * *
```

**Common Examples:**
- `0 2 * * *` - Every day at 2:00 AM
- `0 */6 * * *` - Every 6 hours
- `30 3 * * 0` - Every Sunday at 3:30 AM
- `0 0 1 * *` - First day of every month at midnight

**Example CronJob Configuration:**

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: backup-cronjob
  namespace: my-web-namespace
spec:
  schedule: "0 2 * * *"  # Every day at 2:00 AM
  concurrencyPolicy: Forbid  # Prevent overlapping executions
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: backup-utility:1.0
            command: ["./backup.sh"]
          restartPolicy: OnFailure
      backoffLimit: 3
```

**Useful Commands:**

```bash
# Create a cronjob
kubectl apply -f k8s-cronjob.yaml

# List cronjobs
kubectl get cronjobs -n my-web-namespace

# Get detailed cronjob information
kubectl describe cronjob backup-cronjob -n my-web-namespace

# View triggered jobs
kubectl get jobs -n my-web-namespace

# View cronjob logs (get the pod from the job)
kubectl logs <pod-name> -n my-web-namespace

# Suspend a cronjob (prevent new jobs from being created)
kubectl patch cronjob backup-cronjob -p '{"spec":{"suspend":true}}' -n my-web-namespace

# Resume a suspended cronjob
kubectl patch cronjob backup-cronjob -p '{"spec":{"suspend":false}}' -n my-web-namespace

# Delete a cronjob
kubectl delete cronjob backup-cronjob -n my-web-namespace
```

## concurrencyPolicy Options

The `concurrencyPolicy` field in CronJob specifications controls how Kubernetes handles overlapping job executions. This is crucial for preventing overlapping jobs, especially in scenarios like d[...]

### Three Available Options:

#### 1. **Allow** (Default)
If the previous Job is still running when the next scheduled time arrives, a new Job is created anyway, allowing both to run simultaneously.

**When to use:**
- Independent, parallel-safe tasks
- Data processing that can run multiple instances
- Non-destructive operations

**Example:**
```yaml
concurrencyPolicy: Allow
```

**Scenario:** If a 2 AM backup is still running at 2 AM the next day, it starts a second one anyway.

**Pros:**
- Ensures scheduled tasks always run
- Good for tasks that need to complete regardless

**Cons:**
- Can cause resource contention
- Potential data consistency issues
- Not recommended for I/O intensive tasks

---

#### 2. **Forbid** (Highly Recommended for Backups/Databases)
If the previous Job is still running when the next scheduled time arrives, the new Job creation is skipped for that cycle.

**When to use:**
- Database backups
- Database maintenance operations
- Any operation with exclusive resource requirements
- Tasks that cannot run concurrently
- Critical maintenance tasks

**Example:**
```yaml
concurrencyPolicy: Forbid
```

**Scenario:** If the 2 AM backup is still running at 2 AM the next day, the next scheduled backup is skipped.

**Pros:**
- Prevents resource exhaustion
- Ensures data consistency
- Avoids lock conflicts in databases
- Recommended for backups and database operations

**Cons:**
- Tasks might get skipped if previous execution is slow
- Requires monitoring to ensure tasks aren't consistently missed

---

#### 3. **Replace**
If the previous Job is still running when the next scheduled time arrives, the previous Job is terminated and a new one is started.

**When to use:**
- Health checks
- Monitoring tasks
- Non-critical status updates
- Tasks where only the latest run is needed
- Cleanup operations

**Example:**
```yaml
concurrencyPolicy: Replace
```

**Scenario:** If the 2 AM backup is still running at 2 AM the next day, the existing backup is killed and a new one is started.

**Pros:**
- Ensures latest task always runs
- Prevents queue buildup
- Good for status checks

**Cons:**
- Interrupts long-running operations
- May cause incomplete backups
- Data loss risk for critical operations
- Not recommended for backups or database operations

---

### Comparison Table

| Policy | Overlapping Behavior | Resource Usage | Data Safety | Recommended Use |
|--------|----------------------|-----------------|-------------|-----------------|
| **Allow** | Both run | High (potential spike) | Lower | Independent, parallel-safe tasks |
| **Forbid** | Skip new execution | Normal | High | Backups, database operations ⭐ |
| **Replace** | Kill old, start new | Normal | Lower | Health checks, monitoring |

---

### Best Practices

1. **For Backups & Database Operations**: Always use `Forbid`
   ```yaml
   concurrencyPolicy: Forbid
   ```

2. **Monitor Job Duration**: Set appropriate timeout values
   ```yaml
   spec:
     activeDeadlineSeconds: 3600  # 1 hour timeout
   ```

3. **Add Failure Notifications**: Monitor missed runs and failures
   ```bash
   kubectl get cronjob -n my-web-namespace -o wide
   ```

4. **Log Job Execution**: Always check job history
   ```bash
   kubectl get jobs -n my-web-namespace --sort-by=.metadata.creationTimestamp
   ```

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
kubectl scale deployment my-web-app -n my-web-namespace --replicas=1
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

If you want to run a simple Python script that reads an environment variable named GREETING, you can add a small script to the repository and set the environment variable on your pod or deploymen[...]

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

After applying the change, you can exec into a pod that has Python (or add a sidecar/container that runs Python) to read the variable. Alternatively, set the env var on a debug pod that uses a Py[...]

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

### Job/CronJob not running

```bash
# Check if cronjob is suspended
kubectl get cronjob backup-cronjob -n my-web-namespace

# Check recent job executions
kubectl get jobs -n my-web-namespace --sort-by=.metadata.creationTimestamp

# View job details and events
kubectl describe job <job-name> -n my-web-namespace

# Check for concurrency policy issues
kubectl describe cronjob backup-cronjob -n my-web-namespace
```

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for improvements.

## License

This project is licensed under the **Apache License 2.0** - see the [LICENSE](./LICENSE) file for details.

---

**Keywords**: yaml, kubernetes, deployment, nginx, k8s, container, orchestration, job, cronjob, scheduling
