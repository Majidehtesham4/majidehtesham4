# ERPNext + iran_erp image. Build from the erpnext-iran directory:
#   docker build -t iran-erp:latest .
ARG ERPNEXT_VERSION=v16.50.0
FROM frappe/erpnext:${ERPNEXT_VERSION}

COPY --chown=1000:0 apps/iran_erp /home/frappe/frappe-bench/apps/iran_erp

RUN cd /home/frappe/frappe-bench \
	&& uv pip install --quiet -e apps/iran_erp --python env/bin/python \
	&& ls -1 apps > sites/apps.txt \
	# The image keeps built assets in ../assets; sites/assets is only linked to it at runtime
	&& ln -sfn /home/frappe/frappe-bench/assets sites/assets \
	&& bench build --app iran_erp \
	&& rm sites/assets
