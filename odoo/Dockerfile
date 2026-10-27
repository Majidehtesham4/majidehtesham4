# Odoo 19 with what ERP-VERON reads documents and voices with, without any AI:
# - Tesseract OCR with Persian and English, and poppler to turn the pages of a scanned PDF into images;
# - libheif to open HEIC and AVIF photos (phones and the web save them, often named .jpg);
# - ffmpeg and Vosk for speech to text on the server; its Persian model is fetched by «odoo.ps1 voice».
# PIP_INDEX_URL (in .env) points pip at a mirror when PyPI is not reachable; without Vosk the image is still made
# and voice messages are typed or read by an AI service.
FROM odoo:19.0
ARG PIP_INDEX_URL=""
USER root
RUN apt-get update \
	&& apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fas tesseract-ocr-eng poppler-utils \
		libheif-examples libheif-plugin-libde265 libheif-plugin-dav1d ffmpeg \
	&& rm -rf /var/lib/apt/lists/*
RUN pip3 install --no-cache-dir --break-system-packages ${PIP_INDEX_URL:+--index-url "$PIP_INDEX_URL"} "vosk==0.3.45" \
	|| echo "Vosk could not be fetched: voice messages are not turned into text on the server"
USER odoo
