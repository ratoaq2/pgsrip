FROM debian:trixie-slim AS tesseract-image

ENV TESSDATA_VERSION=main

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /data

RUN git clone --progress --depth 1 --branch ${TESSDATA_VERSION} https://github.com/tesseract-ocr/tessdata_best.git \
    && rm -rf tessdata_best/.git \
    && mv tessdata_best tessdata


FROM debian:trixie-slim AS apt-keys

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gpg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://notesalexp.org/debian/alexp_key.asc | gpg --dearmor > /etc/apt/trusted.gpg.d/alex-p-ubuntu-tesseract-ocr5.gpg \
    && curl -sSL -o /usr/share/keyrings/gpg-pub-moritzbunkus.gpg https://mkvtoolnix.download/gpg-pub-moritzbunkus.gpg


FROM ghcr.io/astral-sh/uv:0.12.15 AS uv

FROM python:3.14-slim AS builder

ENV PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=uv /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE /app/
COPY pgsrip/ /app/pgsrip/
RUN uv build


FROM python:3.14-slim

ENV PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    TESSDATA_PREFIX=/usr/src/tessdata \
    PGSRIP_RAPIDOCR_DIR=/usr/src/rapidocr

COPY --from=apt-keys /etc/apt/trusted.gpg.d/alex-p-ubuntu-tesseract-ocr5.gpg /etc/apt/trusted.gpg.d/
COPY --from=apt-keys /usr/share/keyrings/gpg-pub-moritzbunkus.gpg /usr/share/keyrings/

RUN echo "deb https://notesalexp.org/tesseract-ocr5/trixie/ trixie main" >> /etc/apt/sources.list \
    && echo "deb [signed-by=/usr/share/keyrings/gpg-pub-moritzbunkus.gpg] https://mkvtoolnix.download/debian/ trixie main" >> /etc/apt/sources.list.d/mkvtoolnix.download.list \
    && echo "deb-src [signed-by=/usr/share/keyrings/gpg-pub-moritzbunkus.gpg] https://mkvtoolnix.download/debian/ trixie main" >> /etc/apt/sources.list.d/mkvtoolnix.download.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg tesseract-ocr mkvtoolnix \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=tesseract-image /data/tessdata ${TESSDATA_PREFIX}
COPY --from=builder /app/dist /usr/src/dist

RUN pip install "$(ls /usr/src/dist/pgsrip-*.tar.gz)[rapidocr]"

# the PP-OCRv6 small model: the RapidOCR model of the Latin-script languages, Chinese and Japanese
RUN python -c "from babelfish import Language; from pgsrip.engines.rapidocr import RapidOcrEngine; \
engine = RapidOcrEngine(); engine.prepare([Language('eng')], print); assert engine.supports(Language('eng'))"

WORKDIR /data
VOLUME ${TESSDATA_PREFIX} ${PGSRIP_RAPIDOCR_DIR}

ENTRYPOINT ["pgsrip"]
CMD ["--help"]
