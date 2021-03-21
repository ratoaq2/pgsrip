FROM python:3.9-slim

RUN apt-get update \
 && apt-get install -y wget \
 && wget -O /usr/share/keyrings/gpg-pub-moritzbunkus.gpg https://mkvtoolnix.download/gpg-pub-moritzbunkus.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/gpg-pub-moritzbunkus.gpg] https://mkvtoolnix.download/debian/ buster main" >> /etc/apt/sources.list.d/mkvtoolnix.download.list \
 && echo "deb-src [signed-by=/usr/share/keyrings/gpg-pub-moritzbunkus.gpg] https://mkvtoolnix.download/debian/ buster main" >> /etc/apt/sources.list.d/mkvtoolnix.download.list \
 && apt-get update \
 && apt-get install git ffmpeg libsm6 libxext6 tesseract-ocr mkvtoolnix -y \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /usr/src/app /data \
 && cd /usr/src \
 && git clone https://github.com/tesseract-ocr/tessdata_best.git \
 && mv /usr/src/tessdata_best /usr/src/tessdata \
 && rm -rf /usr/src/tessdata/.git

COPY . /usr/src/app
RUN cd /usr/src/app \
 && pip install --no-cache-dir -r requirements.txt

WORKDIR /data
VOLUME /usr/src/tessdata
ENV TESSDATA_PREFIX=/usr/src/tessdata

ENTRYPOINT ["pgsrip"]
CMD ["--help"]
