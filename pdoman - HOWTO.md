# Podman AI Lab model server — setup & troubleshooting (this machine)

How `http://localhost:44875/v1/chat/completions` (qwen2.5-3B GGUF via llama-server in Podman) was made to work.

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
  - Extra libs copied into image + `LD_LIBRARY_PATH=/usr/local/lib`: libgomp, libssl, libcrypto, libstdc++, libzstd
- Container: `llama-server-avx`
  ```bash
  podman create --name llama-server-avx \
    --network host \
    --entrypoint /usr/local/bin/llama-server \
    -v /home/figura/ai-models/qwen2.5-3b-instruct-Q4_K_M.gguf:/models/qwen2.5-3b-instruct-Q4_K_M.gguf:ro \
    localhost/llama-server-avx:avx \
    --host 0.0.0.0 --port 44875 -m /models/qwen2.5-3b-instruct-Q4_K_M.gguf
  ```
- Start:
  ```bash
  systemd-run -M figura@.host --user --uid=figura --wait /usr/bin/podman start llama-server-avx
  ```
- Test:
  ```bash
  curl http://localhost:44875/v1/chat/completions -H 'Content-Type: application/json' \
    -d '{"messages":[{"role":"system","content":"You are a helpful assistant."},{"role":"user","content":"What is the capital of France?"}]}'
  ```

## Rebuild from scratch

```bash
# as root: toolchain
apt-get install -y cmake

# as figura: clone + configure + build (~20 min on 2 cores)
git clone --depth 1 https://github.com/ggml-org/llama.cpp /tmp/llama-src
cmake -S /tmp/llama-src -B /tmp/llama-build -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=OFF -DGGML_AVX=ON -DGGML_F16C=ON -DGGML_SSE42=ON \
  -DGGML_AVX2=OFF -DGGML_FMA=OFF -DGGML_BMI2=OFF \
  -DLLAMA_CURL=OFF -DBUILD_SHARED_LIBS=OFF
cmake --build /tmp/llama-build --target llama-server -j2
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
cp /tmp/llama-build/bin/llama-server context/
cp -L /usr/lib/x86_64-linux-gnu/{libgomp.so.1,libssl.so.3,libcrypto.so.3,libstdc++.so.6,libzstd.so.1} context/libs/
podman build --isolation=chroot -t localhost/llama-server-avx:avx context
```

## Notes

- Old broken container `eloquent_hofstadter` (ramalama image) can be removed: `podman rm eloquent_hofstadter`
- Performance expectation: ~0.6–1.8 tok/s (2 cores, Q4_K_M 3B, CPU-only; `ggml_vulkan: No devices found` is normal)
- Related containers: `llama-stack-*` belong to the AI Lab / Desktop app and route inference back to the model server on 44875
