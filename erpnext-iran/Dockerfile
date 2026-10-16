# ERPNext + iran_erp image. Build from the erpnext-iran directory:
#   docker build -t iran-erp:latest .
ARG ERPNEXT_VERSION=v16.50.0
FROM frappe/erpnext:${ERPNEXT_VERSION}

COPY --chown=1000:0 apps/iran_erp /home/frappe/frappe-bench/apps/iran_erp

RUN cd /home/frappe/frappe-bench \
	&& uv pip install --quiet -e apps/iran_erp --python env/bin/python \
	&& ls -1 apps > sites/apps.txt \
	# ERPNext lists charts of accounts only from its own folder; this lets the setup wizard offer the Iranian one
	&& cp apps/iran_erp/iran_erp/accounts/ir_iran_chart_of_accounts.json apps/erpnext/erpnext/accounts/doctype/account/chart_of_accounts/verified/ \
	# The image keeps built assets in ../assets; sites/assets is only linked to it at runtime
	&& ln -sfn /home/frappe/frappe-bench/assets sites/assets \
	&& bench build --app iran_erp \
	# The Persian translations, compiled into the image so that every container (web, workers,
	# scheduler) has them; a worker without them rebuilt the shared translation cache without them
	&& bench compile-po-to-mo --app iran_erp --force \
	&& rm sites/assets
