// Small changes to how fields behave on every form.

// A link field («مشتری»، «مدل خودرو»، ...) that already has a value lists only that value when
// clicked, so the user had to delete it to see the others. Now a click lists every choice, as on
// an empty field; the text is selected, so typing searches as before.
(() => {
	const ControlLink = frappe.ui.form.ControlLink;
	const make_input = ControlLink.prototype.make_input;
	ControlLink.prototype.make_input = function () {
		make_input.call(this);
		this.$input.on("focus", () => {
			if (!this.$input.val() || this.df.read_only) return;
			this.$input.select();
			// on_input searches with the text of the event it is given: none, so everything
			this.on_input({ target: { value: "" } });
		});
	};
})();

// Iranian number plates: «۱۲ ب ۳۴۵ ایران ۶۷», entered in four boxes and shown like the plate.
// Kept in the field as «12 ب 345 ایران 67» (iran_dealership/plate.py checks it on save).
iran_erp.plate = {
	LETTERS: ["الف", "ب", "پ", "ت", "ث", "ج", "د", "ز", "ژ", "س", "ش", "ص", "ط", "ع", "ف", "ق", "ک", "گ", "ل", "م", "ن", "و", "ه", "ی", "D", "S"],

	parse(text) {
		const latin = iran_erp.to_latin_digits(String(text || "")).replace(/\s+/g, " ").trim();
		const match = latin.match(/^(\d{2}) ?(الف|[^\d\s]) ?(\d{3}) ?(?:-|ایران)? ?(\d{2})$/);
		if (!match || !this.LETTERS.includes(match[2])) return null;
		return { left: match[1], letter: match[2], middle: match[3], city: match[4] };
	},

	// The plate drawn like the real one; plain text when it is not a plate
	html(text) {
		const p = this.parse(text);
		const fa = iran_erp.to_persian_digits;
		if (!p) return frappe.utils.escape_html(fa(text || ""));
		return `<span class="iran-plate" dir="ltr">
			<span class="iran-plate-flag"><i></i><b>I.R.<br>IRAN</b></span>
			<span class="iran-plate-number">${fa(p.left)}<em>${p.letter}</em>${fa(p.middle)}</span>
			<span class="iran-plate-city"><small>ایران</small>${fa(p.city)}</span>
		</span>`;
	},

	// The four boxes in place of the plate field's text box, on a form
	editor(frm, fieldname = "plate") {
		const field = frm.fields_dict[fieldname];
		if (!field) return;
		const $wrapper = field.$wrapper.addClass("iran-plate-field");
		$wrapper.find(".iran-plate-editor").remove();
		const editable = Boolean(frm.perm[field.df.permlevel || 0]?.write) && !field.df.read_only;
		const fa = iran_erp.to_persian_digits;
		const p = this.parse(frm.doc[fieldname]) || { left: "", letter: "", middle: "", city: "" };
		if (!editable) {
			$(`<div class="iran-plate-editor">${frm.doc[fieldname] ? this.html(frm.doc[fieldname]) : "—"}</div>`).appendTo(
				$wrapper.find(".form-group")
			);
			return;
		}
		const letters = this.LETTERS.map((l) => `<option ${l === p.letter ? "selected" : ""}>${l}</option>`).join("");
		const $editor = $(`<div class="iran-plate-editor">
			<span class="iran-plate" dir="ltr">
				<span class="iran-plate-flag"><i></i><b>I.R.<br>IRAN</b></span>
				<span class="iran-plate-number">
					<input data-part="left" maxlength="2" inputmode="numeric" placeholder="۱۲" value="${fa(p.left)}">
					<select data-part="letter"><option value=""></option>${letters}</select>
					<input data-part="middle" maxlength="3" inputmode="numeric" placeholder="۳۴۵" value="${fa(p.middle)}">
				</span>
				<span class="iran-plate-city"><small>ایران</small>
					<input data-part="city" maxlength="2" inputmode="numeric" placeholder="۶۷" value="${fa(p.city)}">
				</span>
			</span>
		</div>`).appendTo($wrapper.find(".form-group"));
		const parts = ["left", "letter", "middle", "city"];
		const read = () => Object.fromEntries(parts.map((k) => [k, iran_erp.to_latin_digits($editor.find(`[data-part=${k}]`).val() || "").trim()]));
		const save = () => {
			const v = read();
			const filled = parts.filter((k) => v[k]);
			if (!filled.length) return frm.set_value(fieldname, "");
			if (filled.length === parts.length) frm.set_value(fieldname, `${v.left} ${v.letter} ${v.middle} ایران ${v.city}`);
		};
		$editor.find("input").on("input", function () {
			// Digits only, written in Persian; the next box when this one is full
			const digits = iran_erp.to_latin_digits(this.value).replace(/\D/g, "").slice(0, Number(this.maxLength));
			this.value = fa(digits);
			if (digits.length === Number(this.maxLength)) {
				const next = $editor.find("input, select").get($editor.find("input, select").index(this) + 1);
				next && next.focus();
			}
			save();
		});
		$editor.find("select").on("change", function () {
			save();
			$editor.find("[data-part=middle]").focus();
		});
	},
};
