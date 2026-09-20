FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/data/huggingface

WORKDIR /app

RUN groupadd --gid 10001 guardrail \
    && useradd --uid 10001 --gid guardrail --create-home guardrail \
    && mkdir -p /app/data /app/models \
    && chown -R guardrail:guardrail /app/data /app/models

COPY pyproject.toml README.md ./
COPY src ./src

# Container inference uses the profiled CPU runtime and does not need CUDA libraries.
RUN python -m pip install --upgrade pip \
    && python -m pip install \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        'torch==2.14.0+cpu' \
    && python -m pip install '.[ml,pii,onnx]' \
    && python -m pip install \
        'https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl'

COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts

USER guardrail

EXPOSE 8000

CMD ["python", "-m", "guardrail_mini"]
