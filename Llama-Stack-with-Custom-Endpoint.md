# Rebuilding llama-server + Llama Stack with Custom Endpoint

Step-by-step guide for rebuilding llama-server from source and connecting it to Podman Desktop's AI Lab on this machine.

## Why rebuild?

Every prebuilt llama.cpp image (ramalama, etc.) is compiled on modern CPUs with AVX2/FMA/BMI2.
This machine has an Intel Xeon E5-1650 v2 (Ivy Bridge) which only supports AVX, F16C, SSE4.2.
Prebuilt images crash immediately with `Illegal instruction`.

## What we built

- **llama-server** binary compiled from source with Ivy Bridge-compatible flags
- **Container image** `localhost/llama-server-avx:avx` (ubuntu:26.04 base)
- **Running container** serving `qwen2.5-3b-instruct-Q4_K_M.gguf` on port 44876
- **AI Lab config** updated to point at the custom endpoint

---

## Step 1: Rebuild llama-server binary

### Clone llama.cpp (skip if already cloned)

```bash
git clone --depth 1 https://github.com/ggml-org/llama.cpp /home/figura/llama.cpp
```

### Configure with Ivy Bridge flags

```bash
cmake -S /home/figura/llama.cpp -B /home/figura/llama.cpp/build-avx -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=OFF \
  -DGGML_AVX=ON \
  -DGGML_F16C=ON \
  -DGGML_SSE42=ON \
  -DGGML_AVX2=OFF \
  -DGGML_FMA=OFF \
  -DGGML_BMI2=OFF \
  -DLLAMA_CURL=OFF \
  -DBUILD_SHARED_LIBS=OFF
```

Key flags:
- `GGML_NATIVE=OFF` — don't auto-detect CPU features (would pick up AVX2 on build hosts)
- `GGML_AVX=ON` — Ivy Bridge has AVX
- `GGML_F16C=ON` — Ivy Bridge has F16C
- `GGML_SSE42=ON` — Ivy Bridge has SSE4.2
- `GGML_AVX2=OFF` — Ivy Bridge does NOT have AVX2
- `GGML_FMA=OFF` — Ivy Bridge does NOT have FMA
- `GGML_BMI2=OFF` — CMake adds `-mbmi2` by default even with AVX2 off, must set explicitly
- `BUILD_SHARED_LIBS=OFF` — static build, fewer runtime dependencies

### Build llama-server (~20 min on 2 cores)

```bash
cmake --build /home/figura/llama.cpp/build-avx --target llama-server -j2
```

### Verify

```bash
file /home/figura/llama.cpp/build-avx/bin/llama-server
# Should show: ELF 64-bit LSB pie executable, x86-64, dynamically linked

grep -E "AVX|F16C|SSE42|AVX2|FMA|BMI2" /home/figura/llama.cpp/build-avx/CMakeCache.txt
# Should show: GGML_AVX=ON, GGML_F16C=ON, GGML_SSE42=ON, GGML_AVX2=OFF, GGML_FMA=OFF, GGML_BMI2=OFF
```

---

## Step 2: Create Containerfile and build image

### Create build context

```bash
mkdir -p /tmp/opencode/llama-avx/context/libs
```

### Copy binary and libraries

```bash
cp /home/figura/llama.cpp/build-avx/bin/llama-server /tmp/opencode/llama-avx/context/
cp -L /usr/lib/x86_64-linux-gnu/{libgomp.so.1,libssl.so.3,libcrypto.so.3,libstdc++.so.6,libzstd.so.1,libm.so.6,libgcc_s.so.1,libc.so.6,libz.so.1} /tmp/opencode/llama-avx/context/libs/
```

Why copy libraries? The binary is dynamically linked against host glibc (2.43).
Ubuntu 26.04 has the same glibc, so we copy the libs to avoid missing dependencies.

### Create Containerfile

```bash
cat > /tmp/opencode/llama-avx/context/Containerfile << 'EOF'
FROM ubuntu:26.04
COPY llama-server /usr/local/bin/llama-server
COPY libs /usr/local/lib
ENV LD_LIBRARY_PATH=/usr/local/lib
ENTRYPOINT ["/usr/local/bin/llama-server", "--host", "0.0.0.0", "--port", "8000"]
CMD ["-m", "/models/model.gguf"]
EOF
```

### Build image

```bash
podman build --isolation=chroot -t localhost/llama-server-avx:avx /tmp/opencode/llama-avx/context/
```

`--isolation=chroot` is needed because this machine doesn't support user namespace isolation for builds.

---

## Step 3: Create and start container

### Remove old container (if exists)

```bash
podman rm -f llama-server-avx
```

### Create container

```bash
podman create --name llama-server-avx \
  --network host \
  --entrypoint /usr/local/bin/llama-server \
  -v /home/figura/ai-models/qwen2.5-3b-instruct-Q4_K_M.gguf:/models/qwen2.5-3b-instruct-Q4_K_M.gguf:ro \
  localhost/llama-server-avx:avx \
  --host 0.0.0.0 --port 44876 -m /models/qwen2.5-3b-instruct-Q4_K_M.gguf
```

Why these flags:
- `--network host` — bind directly to host network (more reliable than `-p` port publishing)
- `--entrypoint` — override default to pass flags directly
- `-v ...:ro` — mount model read-only
- `--port 44876` — port 44875 is used by Podman Desktop's built-in AI Lab server

### Start container

```bash
podman start llama-server-avx
```

### Verify it's running

```bash
podman ps --filter name=llama-server-avx
# Should show: Up, status running
```

---

## Step 4: Verify the endpoint

### Health check

```bash
curl http://localhost:44876/health
# Should return: {"status":"ok"}
```

### List models

```bash
curl http://localhost:44876/v1/models
# Should show: qwen2.5-3b-instruct-Q4_K_M.gguf
```

### Test chat completions (OpenAI-compatible API)

```bash
curl http://localhost:44876/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"system","content":"You are a helpful assistant."},{"role":"user","content":"What is the capital of France?"}]}'
# Should return: "The capital of France is Paris."
```

---

## Step 5: Configure AI Lab to use the custom endpoint

### Update Podman Desktop settings

Edit `~/.config/containers/podman-desktop/settings.json`:

```json
{
  "ai-lab.apiPort": 44876,
  "ai-lab.models.path": "/home/figura/ai-models",
  "ai-lab.inferenceRuntime": "llama-cpp"
}
```

The AI Lab extension in Podman Desktop will now connect to port 44876 instead of trying to start its own model server.

### Restart Podman Desktop

```bash
su - figura -c 'export PATH=/opt/node24/bin:$PATH && export DISPLAY=:0 && export XAUTHORITY=/run/user/1000/.mutter-Xwaylandauth.* && cd /home/figura/podman-desktop && pnpm watch'
```

---

## Troubleshooting

### Container exits immediately

```bash
podman logs llama-server-avx
# Check for "Illegal instruction" — wrong CPU flags
# Check for port already in use — change port
```

### Port 44875 already in use

```bash
ss -tlnp | grep 44875
# Podman Desktop's Electron process holds this port
# Use port 44876 instead (or kill the Electron process first)
```

### X auth error when starting Podman Desktop

```bash
# The XAUTHORITY path changes per login. Use glob:
export XAUTHORITY=/run/user/1000/.mutter-Xwaylandauth.*
```

### Container won't start from CLI (polkit error)

```bash
# Use systemd-run to start in user session:
systemd-run -M figura@.host --user --uid=figura --wait /usr/bin/podman start llama-server-avx
```

---

## Performance

- ~0.6-1.8 tok/s on 2 cores, Q4_K_M 3B, CPU-only
- `ggml_vulkan: No devices found` is normal (no GPU)
- The model uses ~1.8GB RAM
