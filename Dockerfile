FROM python:3.13-slim AS tesseract-image

ENV TESSDATA_VERSION=main

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /data

RUN git clone --progress --depth 1 --branch ${TESSDATA_VERSION} https://github.com/tesseract-ocr/tessdata_best.git \
    && rm -rf tessdata_best/.git \
    && mv tessdata_best tessdata


FROM python:3.13-slim AS builder

ENV PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_VERSION=1.8.3 \
    POETRY_VIRTUALENVS_CREATE=0

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gpg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip install "poetry==$POETRY_VERSION"

WORKDIR /app
COPY poetry.lock pyproject.toml README.md /app/
RUN poetry install --no-interaction --no-ansi --only main
COPY pgsrip/ /app/pgsrip/
RUN poetry build --no-interaction --no-ansi


FROM python:3.13-slim

ENV PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    TESSDATA_PREFIX=/usr/src/tessdata

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gpg \
    && curl -sSL https://notesalexp.org/debian/alexp_key.asc | gpg --dearmor > /etc/apt/trusted.gpg.d/alex-p-ubuntu-tesseract-ocr5.gpg \
    && curl -sSL -o /usr/share/keyrings/gpg-pub-moritzbunkus.gpg https://mkvtoolnix.download/gpg-pub-moritzbunkus.gpg \
    && echo "deb https://notesalexp.org/tesseract-ocr5/trixie/ trixie main" >> /etc/apt/sources.list \
    && echo "deb [signed-by=/usr/share/keyrings/gpg-pub-moritzbunkus.gpg] https://mkvtoolnix.download/debian/ trixie main" >> /etc/apt/sources.list.d/mkvtoolnix.download.list \
    && echo "deb-src [signed-by=/usr/share/keyrings/gpg-pub-moritzbunkus.gpg] https://mkvtoolnix.download/debian/ trixie main" >> /etc/apt/sources.list.d/mkvtoolnix.download.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsm6 libxext6 tesseract-ocr mkvtoolnix \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=tesseract-image /data/tessdata ${TESSDATA_PREFIX}
COPY --from=builder /app/dist /usr/src/dist

RUN pip install /usr/src/dist/pgsrip-*.tar.gz

WORKDIR /data
VOLUME ${TESSDATA_PREFIX}

ENTRYPOINT ["pgsrip"]
CMD ["--help"]
