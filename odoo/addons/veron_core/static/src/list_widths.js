/** @odoo-module **/
/**
 * Amounts in rial are long («1,754,500,000 ریال»): Odoo gives a monetary column a fixed width made for
 * «1 million» in euros with cents, so the amounts of a list were cut («2,873,750,0…»). Here an amount
 * column gets the width it needs, between a minimum and a maximum, like a text column.
 */
import { registry } from "@web/core/registry";

const fields = registry.category("fields");
for (const [name, width] of [["monetary", [125, 200]], ["float", [92, 160]], ["list.monetary", [125, 200]]]) {
	if (fields.contains(name)) {
		const field = fields.get(name);
		if (!field.listViewWidth) {
			field.listViewWidth = width;
		}
	}
}
