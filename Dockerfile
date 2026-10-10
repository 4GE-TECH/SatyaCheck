# SatyaCheck API image (upgrade plan, Phase 6).
#
# One image for GPU and CPU. PyTorch's CUDA wheels bring their own CUDA runtime, so the
# host needs only the NVIDIA driver and the container toolkit; without a GPU the same image
# runs on CPU (CLAUDE.md rule 6: GPU is an optimisation, never a requirement).
#
#   docker build -t satyacheck-api .                                   # CUDA 12.8 wheels
#   docker build -t satyacheck-api --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cpu .
#
# Models are not in the image. Mount them read-only at /app/models (and the FAISS index at
# /app/nlp_rag/index); the container makes no network calls at run time (rule 4).

FROM python:3.11-slim-bookworm

ARG TORCH_INDEX=https://download.pytorch.org/whl/cu128

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    SATYACHECK_ENV=production \
    WARM_MODELS=true

# ffmpeg normalises every upload to 16 kHz mono; libsndfile backs soundfile.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Torch first, from the chosen index, so requirements.txt finds it already satisfied.
RUN pip install --index-url "${TORCH_INDEX}" "torch>=2.2.0" "torchaudio>=2.2.0"
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN useradd --create-home --uid 10001 satyacheck \
    && mkdir -p /app/data/sessions /app/data/reports /app/models /app/nlp_rag/index \
    && chown -R satyacheck /app/data
USER satyacheck

EXPOSE 8000

# /api/ready answers 503 until the models are warm, so no call lands on a cold server.
HEALTHCHECK --interval=15s --timeout=5s --start-period=180s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/ready', timeout=4).status == 200 else 1)"

# One worker: models live in process memory, and capacity.py's admission and inference
# slots are per process. Scale with more containers, not more workers.
CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
