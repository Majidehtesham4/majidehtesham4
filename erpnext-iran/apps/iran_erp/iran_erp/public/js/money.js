// Amounts as Iranian accounting writes them: the number, then «ریال» on its left («۳۵٬۰۰۰ ریال»).
//
// The rial is set to be written after the number (install.setup_rial). As plain text in a
// right-to-left page the minus of a negative amount moved to the far side of the number, and in
// the left-to-right number cells of the tables the word went to the other side. The number is
// marked as a left-to-right part inside a right-to-left whole, which keeps «-۳۵٬۰۰۰» together and
// «ریال» on its left wherever the amount is drawn. The server does the same (overrides/money.py).

frappe.provide("iran_erp.money");

// Unicode directional isolates: right-to-left, left-to-right, end of isolate
iran_erp.money.RLI = "⁧";
iran_erp.money.LRI = "⁦";
iran_erp.money.PDI = "⁩";

// «number words» in Persian order: the number on the right, the words to its left
iran_erp.money.isolate = function (number, words) {
	const { RLI, LRI, PDI } = iran_erp.money;
	return `${RLI}${LRI}${number}${PDI} ${words}${PDI}`;
};

// The number and the words of an isolated amount, or null for any other text
iran_erp.money.parts = function (text) {
	const match = /^⁧⁦(.*?)⁩ (.*)⁩$/.exec(String(text || "").trim());
	return match ? { number: match[1], words: match[2] } : null;
};

(function () {
	const base = window.format_currency;
	if (typeof base !== "function" || base.iran_isolated) return;
	window.format_currency = function (v, currency, decimals) {
		const text = base.apply(this, arguments);
		if (typeof text !== "string" || !text) return text;
		const code = currency || (frappe.boot && frappe.boot.sysdefaults && frappe.boot.sysdefaults.currency);
		if (!code || !frappe.model.get_value(":Currency", code, "symbol_on_right")) return text;
		const symbol = window.get_currency_symbol(code);
		const suffix = symbol ? " " + __(symbol) : "";
		if (!suffix || !text.endsWith(suffix)) return text;
		return iran_erp.money.isolate(text.slice(0, -suffix.length), __(symbol));
	};
	window.format_currency.iran_isolated = true;
})();

// Amount fields are labelled with the currency's code («جمع (IRR)»); a currency written after the
// number is named by its word instead («جمع (ریال)»). The form code arrives with the form bundle,
// which loads when the first form opens.
iran_erp.money.currency_name = function (currency) {
	if (!currency || !frappe.model.get_value(":Currency", currency, "symbol_on_right")) return currency;
	return __(frappe.model.get_value(":Currency", currency, "symbol") || currency);
};

iran_erp.money.patch_form = function (Form) {
	if (!Form || !Form.prototype || Form.prototype.iran_currency_labels) return Form;
	const set_currency_labels = Form.prototype.set_currency_labels;
	Form.prototype.set_currency_labels = function (fields_list, currency, parentfield) {
		return set_currency_labels.call(this, fields_list, iran_erp.money.currency_name(currency), parentfield);
	};
	Form.prototype.iran_currency_labels = true;
	return Form;
};

(function () {
	frappe.provide("frappe.ui.form");
	let current = iran_erp.money.patch_form(frappe.ui.form.Form);
	Object.defineProperty(frappe.ui.form, "Form", {
		configurable: true,
		get: () => current,
		set: (value) => (current = iran_erp.money.patch_form(value)),
	});
})();
