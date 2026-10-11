// Jalali (Solar Hijri) display for ERPNext desk.
// Dates are still stored and entered as Gregorian; this only changes how they are shown.

frappe.provide("iran_erp");

iran_erp.jalali_formatter = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
	year: "numeric",
	month: "2-digit",
	day: "2-digit",
});

iran_erp.to_jalali = function (value) {
	// value is a date string in database format: YYYY-MM-DD[ HH:mm:ss]
	const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value || "");
	if (!match) return "";
	const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
	return iran_erp.jalali_formatter.format(date);
};

// List view, report view, read-only fields and grids show the Jalali date.
const gregorian_date_formatter = frappe.form.formatters.Date;
frappe.form.formatters.Date = function (value, ...args) {
	return iran_erp.to_jalali(value) || gregorian_date_formatter.call(this, value, ...args);
};

// Editable date fields keep the Gregorian date picker and show the Jalali date under it.
frappe.ui.form.ControlDate = class ControlJalaliDate extends frappe.ui.form.ControlDate {
	set_formatted_input(value) {
		super.set_formatted_input(value);
		this.set_jalali_hint(value);
	}

	set_jalali_hint(value) {
		if (!this.$wrapper) return;
		if (!this.$jalali_hint) {
			this.$jalali_hint = $(`<div class="iran-erp-jalali-hint text-muted small"></div>`);
			this.$wrapper.find(".control-input-wrapper").append(this.$jalali_hint);
		}
		const jalali = iran_erp.to_jalali(value);
		this.$jalali_hint.text(jalali ? `${__("Jalali")}: ${jalali}` : "");
	}
};
