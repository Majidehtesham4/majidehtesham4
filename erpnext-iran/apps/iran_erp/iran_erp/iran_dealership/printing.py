"""The car's body diagram for printing: the same drawing as the form, coloured by what was found."""

import frappe
from frappe.utils import escape_html

# key: tag, attributes (top view, front at the top), as in iran_vehicle.js
PARTS = {
	"front_bumper": ("rect", 'x="70" y="8" width="160" height="26" rx="13"'),
	"hood": ("rect", 'x="72" y="40" width="156" height="92" rx="12"'),
	"front_left_fender": ("rect", 'x="22" y="44" width="44" height="92" rx="12"'),
	"front_right_fender": ("rect", 'x="234" y="44" width="44" height="92" rx="12"'),
	"windshield": ("path", 'd="M80 138 H220 L208 172 H92 Z"'),
	"front_left_door": ("rect", 'x="22" y="142" width="44" height="94" rx="6"'),
	"front_right_door": ("rect", 'x="234" y="142" width="44" height="94" rx="6"'),
	"roof": ("rect", 'x="92" y="178" width="116" height="150" rx="10"'),
	"rear_left_door": ("rect", 'x="22" y="240" width="44" height="94" rx="6"'),
	"rear_right_door": ("rect", 'x="234" y="240" width="44" height="94" rx="6"'),
	"left_sill": ("rect", 'x="6" y="142" width="12" height="192" rx="5"'),
	"right_sill": ("rect", 'x="282" y="142" width="12" height="192" rx="5"'),
	"rear_glass": ("path", 'd="M92 334 H208 L220 364 H80 Z"'),
	"rear_left_fender": ("rect", 'x="22" y="340" width="44" height="92" rx="12"'),
	"rear_right_fender": ("rect", 'x="234" y="340" width="44" height="92" rx="12"'),
	"trunk": ("rect", 'x="72" y="370" width="156" height="72" rx="12"'),
	"rear_bumper": ("rect", 'x="70" y="448" width="160" height="26" rx="13"'),
}


def body_svg(doc, width=200) -> str:
	keys = dict(frappe.get_all("Iran Body Part", fields=["name", "diagram_key"], as_list=True))
	colors = dict(frappe.get_all("Iran Body Condition", fields=["name", "color_code"], as_list=True))
	found = {}
	for mark in doc.get("body_marks") or []:
		found.setdefault(mark.body_part, []).append(mark.condition)
	shapes = []
	for part, key in keys.items():
		if key not in PARTS:
			continue
		tag, attrs = PARTS[key]
		conditions = found.get(part) or []
		fill = colors.get(conditions[0]) or "#7c3aed" if conditions else "#f3f4f6"
		title = escape_html(part + (": " + "، ".join(conditions) if conditions else ""))
		shapes.append(
			f'<{tag} {attrs} fill="{fill}" stroke="#555" stroke-width="1.5"><title>{title}</title></{tag}>'
		)
	return (
		f'<svg viewBox="0 0 300 482" width="{width}" xmlns="http://www.w3.org/2000/svg">'
		+ "".join(shapes)
		+ "</svg>"
	)


def car_money(value, currency=None) -> str:
	"""An amount the way the desk shows it: Persian digits, no decimals, rial after the number."""
	from frappe.utils import fmt_money

	from iran_erp.utils.jalali import to_persian_digits

	currency = currency or frappe.defaults.get_global_default("currency")
	return to_persian_digits(fmt_money(value or 0, 0, currency))
