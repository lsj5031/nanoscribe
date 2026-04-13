ARG BASE_IMAGE=glm-asr-glm-asr:latest
FROM ${BASE_IMAGE}

USER root

ENV HF_HUB_OFFLINE=0 \
    MODELSCOPE_CACHE=/home/appuser/.cache/modelscope

# Reuse the existing CUDA/PyTorch image and only add the packages FunASR needs.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -U funasr modelscope huggingface huggingface_hub

USER appuser
WORKDIR /app

CMD ["python", "-c", "import funasr; print('FunASR image ready')"]
