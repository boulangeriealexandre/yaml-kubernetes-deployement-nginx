#!/usr/bin/env bash
set -euo pipefail

LLAMA_SERVER="llama-server-avx"
LLAMA_STACK="llama-stack-server"
PATCH_DIR="/home/figura/ai-models/llama-stack-patch"
MODEL_ID="/models/qwen2.5-3b-instruct-Q4_K_M.gguf"

echo "=== Starting AI stack ==="

# 1. Start the model server
if ! podman container exists "$LLAMA_SERVER" 2>/dev/null; then
    echo "ERROR: $LLAMA_SERVER container does not exist. Recreate it first."
    exit 1
fi

STATUS=$(podman inspect --format '{{.State.Status}}' "$LLAMA_SERVER" 2>/dev/null || echo "missing")
if [ "$STATUS" != "running" ]; then
    echo "Starting $LLAMA_SERVER..."
    podman start "$LLAMA_SERVER"
    # Wait for health
    for i in $(seq 1 30); do
        if curl -sf http://localhost:44876/health >/dev/null 2>&1; then
            echo "$LLAMA_SERVER is up on port 44876"
            break
        fi
        sleep 1
    done
else
    echo "$LLAMA_SERVER already running"
fi

# 2. Start the llama-stack server
if ! podman container exists "$LLAMA_STACK" 2>/dev/null; then
    echo "Creating $LLAMA_STACK container..."
    podman create --name "$LLAMA_STACK" \
      --network host \
      --entrypoint llama \
      -v /home/figura/.local/share/containers/podman-desktop/extensions-storage/redhat.ai-lab/llama-stack/container/.llama:/opt/app-root/src/.llama:Z \
      -v "$PATCH_DIR/podman_ai_lab.py":/opt/app-root/lib64/python3.11/site-packages/podman_ai_lab_stack/podman_ai_lab.py:ro,Z \
      -e PODMAN_AI_LAB_URL=http://host.containers.internal:44876 \
      ghcr.io/containers/podman-ai-lab-stack:a06f399ebf7cb2645af126da0e84395db9bb0d1a \
      stack run /opt/app-root/lib64/python3.11/site-packages/podman_ai_lab_stack/run.yaml
fi

STATUS=$(podman inspect --format '{{.State.Status}}' "$LLAMA_STACK" 2>/dev/null || echo "missing")
if [ "$STATUS" != "running" ]; then
    echo "Starting $LLAMA_STACK..."
    podman start "$LLAMA_STACK"
    # Wait for health
    for i in $(seq 1 40); do
        if curl -sf http://localhost:8321/v1/health >/dev/null 2>&1; then
            echo "$LLAMA_STACK is up on port 8321"
            break
        fi
        sleep 1
    done
else
    echo "$LLAMA_STACK already running"
fi

# 3. Verify model is registered
MODELS=$(curl -sf http://localhost:8321/v1/models 2>/dev/null || echo "")
if echo "$MODELS" | grep -q "$MODEL_ID"; then
    echo "Model $MODEL_ID is registered"
else
    echo "Registering model $MODEL_ID..."
    podman exec "$LLAMA_STACK" llama-stack-client models register "$MODEL_ID" --provider-id podman-ai-lab
fi

# 4. Quick test
echo ""
echo "=== Quick test ==="
RESULT=$(curl -sf http://localhost:8321/v1/openai/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"$MODEL_ID\",\"messages\":[{\"role\":\"user\",\"content\":\"Say hi in 3 words\"}],\"max_tokens\":20}" 2>/dev/null)
if [ -n "$RESULT" ]; then
    echo "$RESULT" | python3 -c "import sys,json; r=json.load(sys.stdin); print('Reply:', r['choices'][0]['message']['content'])" 2>/dev/null || echo "$RESULT"
else
    echo "WARNING: Chat completion test failed. Check: podman logs $LLAMA_STACK"
fi

echo ""
echo "=== Done ==="
echo "llama-server-avx:  http://localhost:44876"
echo "llama-stack:       http://localhost:8321"
echo "OpenAI endpoint:   http://localhost:8321/v1/openai/v1/chat/completions"
