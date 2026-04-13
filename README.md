# FunASR Docker

This repo builds a FunASR image by reusing the already-built local GLM-ASR image as its base. That avoids rebuilding CUDA, Python, and PyTorch from scratch.

## Requirements

- Docker
- NVIDIA Container Toolkit for GPU access
- A local base image tagged `glm-asr-glm-asr:latest`

If your local base image uses a different tag, override it when building:

```bash
make build BASE_IMAGE=glm-asr:latest
```

## Build

```bash
make build
```

## Smoke Test

```bash
make smoke
```

## Open A Shell

```bash
make shell
```

This mounts:

- `~/.cache/huggingface`
- `~/.cache/modelscope`
- `./data` to `/app/data`

## Example

Inside the container:

```bash
python - <<'PY'
from funasr import AutoModel

model = AutoModel(model="fsmn-vad")
print(model.generate(input=f"{model.model_path}/example/vad_example.wav"))
PY
```
