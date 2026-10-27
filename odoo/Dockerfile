# Odoo 19 with what ERP-VERON reads documents with, without any AI: Tesseract OCR with Persian and English,
# and poppler to turn the pages of a scanned PDF into images
FROM odoo:19.0
USER root
RUN apt-get update \
	&& apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fas tesseract-ocr-eng poppler-utils \
	&& rm -rf /var/lib/apt/lists/*
USER odoo
