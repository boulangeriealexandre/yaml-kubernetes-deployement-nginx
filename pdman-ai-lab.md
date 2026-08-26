# Podman AI Lab model server — setup & troubleshooting (this machine)

How `http://localhost:44876/v1/chat/completions` (qwen2.5-3B GGUF via llama-server in Podman) was made to work.

## Hardware constraint (root cause)

- CPU: Intel Xeon E5-1650 v2 (Ivy Bridge) — has AVX, F16C, SSE4.2
- **No AVX2, no FMA, no BMI2**
- Every prebuilt llama.cpp / ramalama image (`quay.io/ramalama/ramalama-llama-server`) is compiled on modern runners → dies instantly with `Illegal instruction`
- Any llama.cpp build for this box MUST use: `GGML_AVX=ON GGML_F16C=ON GGML_SSE42=ON GGML_AVX2=OFF GGML_FMA=OFF GGML_BMI2=OFF`
- Gotcha: CMake adds `-mbmi2` by default even with AVX2/FMA off → must explicitly set `GGML_BMI2=OFF` (check `CMakeCache.txt`)

## Environment constraints

- Podman runs as user `figura`; cgroup manager = systemd (user session)
- Starting containers as root or via plain `runuser/su` fails with polkit
  *"requires interactive authentication"* because the caller isn't in figura's login session
- Workarounds:
  - Start from **Podman Desktop GUI** (runs inside the GNOME session), or
  - `systemd-run -M figura@.host --user --uid=figura --wait /usr/bin/podman start <name>`
- `-p` port publishing only binds reliably for containers started by the Desktop app.
  From CLI/systemd-run, use `--network host` and bind the service port directly instead.

## Current working setup

- Image: `localhost/llama-server-avx:avx` (built locally; ubuntu:26.04 base to match host glibc 2.43)
  - Binary: llama.cpp `llama-server`, built on-host with Ivy Bridge flags above
  - Extra libs copied into image + `LD_LIBRARY_PATH=/usr/local/lib`: libgomp, libssl, libcrypto, libstdc++, libzstd, libm, libgcc_s, libc, libz
- Patched provider: `/home/figura/ai-models/llama-stack-patch/` (OpenAI-compatible adapter for llama-stack)
- Containers:
  - `llama-server-avx` — port 44876, serves the GGUF model
  - `llama-stack-server` — port 8321, llama-stack proxy with patched provider
- Quick start after reboot:
  ```bash
  bash /home/figura/ai-models/start-ai.sh
  ```

## Rebuild from scratch

```bash
# as root: toolchain
apt-get install -y cmake

# as figura: clone + configure + build (~20 min on 2 cores)
git clone --depth 1 https://github.com/ggml-org/llama.cpp /home/figura/llama.cpp
cmake -S /home/figura/llama.cpp -B /home/figura/llama.cpp/build-avx -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=OFF -DGGML_AVX=ON -DGGML_F16C=ON -DGGML_SSE42=ON \
  -DGGML_AVX2=OFF -DGGML_FMA=OFF -DGGML_BMI2=OFF \
  -DLLAMA_CURL=OFF -DBUILD_SHARED_LIBS=OFF
cmake --build /home/figura/llama.cpp/build-avx --target llama-server -j2
```

Then rebuild the image (Containerfile lives in `/tmp/opencode/llama-avx/context` — recreate if wiped):

```
FROM ubuntu:26.04
COPY llama-server /usr/local/bin/llama-server
COPY libs /usr/local/lib
ENV LD_LIBRARY_PATH=/usr/local/lib
ENTRYPOINT ["/usr/local/bin/llama-server", "--host", "0.0.0.0", "--port", "8000"]
CMD ["-m", "/models/model.gguf"]
```

```bash
mkdir -p context/libs
cp /home/figura/llama.cpp/build-avx/bin/llama-server context/
cp -L /usr/lib/x86_64-linux-gnu/{libgomp.so.1,libssl.so.3,libcrypto.so.3,libstdc++.so.6,libzstd.so.1,libm.so.6,libgcc_s.so.1,libc.so.6,libz.so.1} context/libs/
podman build --isolation=chroot -t localhost/llama-server-avx:avx context
```

## Notes

- Old broken container `eloquent_hofstadter` (ramalama image) can be removed: `podman rm eloquent_hofstadter`
- Performance expectation: ~0.6–1.8 tok/s (2 cores, Q4_K_M 3B, CPU-only; `ggml_vulkan: No devices found` is normal)

## Architecture (full chain)

```
Podman Desktop AI Lab / playground
        │
        ▼
llama-stack-server  (port 8321, OpenAI-compatible)
        │  uses patched podman_ai_lab.py
        ▼
llama-server-avx   (port 44876, llama.cpp built for AVX)
        │
        ▼
qwen2.5-3b-instruct-Q4_K_M.gguf
```

- **llama-server-avx**: Custom llama.cpp server built for Ivy Bridge (AVX only, no AVX2/FMA/BMI2). Runs on port 44876 with `--network host`.
- **llama-stack-server**: Meta's llama-stack proxy. Runs on port 8321. Uses a patched `podman_ai_lab.py` that talks OpenAI protocol directly to llama-server-avx (bypassing the AI Lab extension API which can't route to manually-started model servers).

## Starting everything

### Quick way (recommended)

```bash
bash /home/figura/ai-models/start-ai.sh
```

### Manual way

#### 1. Start the model server (llama-server-avx)

```bash
# Start the container (from Podman Desktop or CLI):
systemd-run -M figura@.host --user --uid=figura --wait /usr/bin/podman start llama-server-avx
```

Verify it's running:
```bash
curl -s http://localhost:44876/health
# Should return: {"status":"ok"}
```

### 2. Start the llama-stack server

The llama-stack server needs a patched provider to talk OpenAI protocol to our custom llama-server. The patch files live at `/home/figura/ai-models/llama-stack-patch/`.

```bash
# If the patch files don't exist at /home/figura/ai-models/llama-stack-patch/, recreate them (see "Patched provider" section below)

# Create the llama-stack server container:
podman create --name llama-stack-server \
  --network host \
  --entrypoint llama \
  -v /home/figura/.local/share/containers/podman-desktop/extensions-storage/redhat.ai-lab/llama-stack/container/.llama:/opt/app-root/src/.llama:Z \
  -v /home/figura/ai-models/llama-stack-patch/podman_ai_lab.py:/opt/app-root/lib64/python3.11/site-packages/podman_ai_lab_stack/podman_ai_lab.py:ro,Z \
  -e PODMAN_AI_LAB_URL=http://host.containers.internal:44876 \
  ghcr.io/containers/podman-ai-lab-stack:a06f399ebf7cb2645af126da0e84395db9bb0d1a \
  stack run /opt/app-root/lib64/python3.11/site-packages/podman_ai_lab_stack/run.yaml
```

Start it:
```bash
podman start llama-stack-server
```

Wait ~30 seconds for startup, then register the model:
```bash
podman exec llama-stack-server llama-stack-client models register \
  "/models/qwen2.5-3b-instruct-Q4_K_M.gguf" --provider-id podman-ai-lab
```

### 3. Verify the full chain

```bash
# Health check:
curl -s http://localhost:8321/v1/health

# List models:
curl -s http://localhost:8321/v1/models

# Chat completion (OpenAI-compatible):
curl -s http://localhost:8321/v1/openai/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"/models/qwen2.5-3b-instruct-Q4_K_M.gguf","messages":[{"role":"user","content":"Hello"}]}'

# Chat completion (native llama-stack):
curl -s http://localhost:8321/v1/inference/chat-completion \
  -H 'Content-Type: application/json' \
  -d '{"model_id":"/models/qwen2.5-3b-instruct-Q4_K_M.gguf","messages":[{"role":"user","content":"Hello"}]}'
```

## After computer restart

Everything persists (container definitions, model registration, patch files). Just start:

```bash
bash /home/figura/ai-models/start-ai.sh
```

This will:
1. Start `llama-server-avx` (port 44876)
2. Start `llama-stack-server` (port 8321)
3. Register the model if needed
4. Run a quick test

## Patched provider (how it works)

The standard `podman-ai-lab` provider in llama-stack uses the Ollama Python library to talk to the Podman Desktop AI Lab extension API (port 10434). That API only routes to model services that it manages itself — it doesn't know about our manually-started `llama-server-avx`.

**Solution**: Patch `podman_ai_lab.py` to use `httpx` (OpenAI protocol) and point directly at `http://host.containers.internal:44876`.

### Patch files

Located at `/home/figura/ai-models/llama-stack-patch/`:

- **`podman_ai_lab.py`** — Replaces the Ollama-based adapter with an OpenAI-compatible one using `httpx`. Supports:
  - `openai_chat_completion` — forwards to llama-server's `/v1/chat/completions`
  - `chat_completion` — converts llama-stack messages to OpenAI format
  - `completion` — forwards to llama-server's `/v1/completions`
  - Streaming support for all endpoints

### Key differences from the original provider

| Aspect | Original | Patched |
|---|---|---|
| Library | `ollama` (Ollama protocol) | `httpx` (OpenAI protocol) |
| Target | AI Lab API (port 10434) | llama-server-avx (port 44876) |
| Model registration | Managed by AI Lab extension | Manual via `llama-stack-client` |

### To recreate the patch files

If `/home/figura/ai-models/llama-stack-patch/` is wiped, the patched `podman_ai_lab.py` must be recreated. The key changes from the original:

1. Replace `from ollama import AsyncClient` with `import httpx` and `import json`
2. Change `__init__` to store a URL and create an `httpx.AsyncClient`
3. Implement `openai_chat_completion` that serializes pydantic messages and forwards to `/v1/chat/completions`
4. Implement `chat_completion` that converts llama-stack messages to OpenAI format
5. Return `OpenAIChatCompletion` / `OpenAIChatCompletionChunk` objects (not raw dicts)

### The provider YAML

Must be placed at `~/.llama/providers.d/remote/inference/podman-ai-lab.yaml`:

```yaml
adapter:
  adapter_type: podman-ai-lab
  config_class: podman_ai_lab_stack.config.PodmanAILabImplConfig
  module: podman_ai_lab_stack
api_dependencies: []
optional_api_dependencies: []
```

This is the same as the original — only the Python implementation changes.

## Removing old containers

```bash
podman rm -f llama-stack-server 2>/dev/null
podman rm eloquent_hofstadter 2>/dev/null
```
