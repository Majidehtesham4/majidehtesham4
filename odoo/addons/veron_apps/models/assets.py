"""Large numbers of spreadsheets and dashboards shortened in Persian words: «150 میلیون» for 150m.

o-spreadsheet writes k, m and b with no way to change them from outside, so its file is adjusted where Odoo
reads it for the asset bundle: the shortening asks globalThis.veronLargeNumbers (set in Persian by
static/src/spreadsheet/shamsi.js) first. A later o-spreadsheet without these lines is left as it is."""

import logging

from odoo.addons.base.models.assetsbundle import JavascriptAsset

_logger = logging.getLogger(__name__)

FILE = "/spreadsheet/static/src/o_spreadsheet/o_spreadsheet.js"
ORIGINAL = """	if (value < 1e5) return createLargeNumberFormat(format, 0, "", locale);
	else if (value < 1e8) return createLargeNumberFormat(format, 1, "k", locale);
	else if (value < 1e11) return createLargeNumberFormat(format, 2, "m", locale);
	return createLargeNumberFormat(format, 3, "b", locale);"""
PERSIAN = """	const veron = globalThis.veronLargeNumbers?.(value);
	if (veron) return createLargeNumberFormat(format, veron.magnitude, veron.postFix, locale);
""" + ORIGINAL

_fetch_content = JavascriptAsset._fetch_content


def _veron_fetch_content(self):
	content = _fetch_content(self)
	if self.url and self.url.endswith(FILE):
		if ORIGINAL in content:
			content = content.replace(ORIGINAL, PERSIAN, 1)
		else:
			_logger.warning("ERP-VERON: o-spreadsheet's large numbers have changed, kept in English")
	return content


JavascriptAsset._fetch_content = _veron_fetch_content
