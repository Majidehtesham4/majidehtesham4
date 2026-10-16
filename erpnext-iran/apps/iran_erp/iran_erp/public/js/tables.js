// Report tables (frappe DataTable) sized to what they hold.
//
// The table sizes a column from its header and its first row only, and keeps any width the report
// sets; values further down were cut («246,200,293,...») while other tables were wider than needed
// and scrolled sideways for nothing. Here every column gets the width of its longest header or
// value among the first rows (indented tree rows included), within limits; when the columns
// together are narrower than the page they are widened to fill it, so the table scrolls sideways
// only when its content really is wider than the page.

frappe.provide("iran_erp.tables");

iran_erp.tables.SAMPLE_ROWS = 300;
iran_erp.tables.MIN_WIDTH = 70;
iran_erp.tables.MAX_WIDTH = 420;
iran_erp.tables.PADDING = 34;
// Canvas measures come out a little narrower than the table draws the same text
iran_erp.tables.SCALE = 1.08;
iran_erp.tables.INDENT = 20;

iran_erp.tables.measure = (function () {
	let context = null;
	return function (text, bold) {
		if (!context) context = document.createElement("canvas").getContext("2d");
		const style = getComputedStyle(document.body);
		context.font = `${bold ? 600 : 400} 13px ${style.fontFamily}`;
		const value = String(text);
		// Digits are drawn as Persian digits, which are a little wider than the ones measured here
		const digits = document.documentElement.dir === "rtl" ? (value.match(/\d/g) || []).length : 0;
		return context.measureText(value).width + digits * 1.9;
	};
})();

iran_erp.tables.text = function (html) {
	if (html === null || html === undefined) return "";
	const value = String(html);
	if (!value.includes("<")) return value;
	const div = document.createElement("div");
	div.innerHTML = value;
	return div.textContent || "";
};

// The text a cell will show: through the column's own formatter when it has one
iran_erp.tables.cell_text = function (column, value, row) {
	if (value === null || value === undefined || value === "") return "";
	try {
		if (typeof column.format === "function") {
			return iran_erp.tables.text(column.format(value, row, column, row));
		}
		if (column.docfield || column.fieldtype) {
			const df = column.docfield || { fieldtype: column.fieldtype, options: column.options };
			return iran_erp.tables.text(frappe.format(value, df, { always_show_decimals: false }, row));
		}
	} catch (e) {
		// Formatters written for the full row may fail on the raw values; the value itself is close
	}
	return typeof value === "object" ? iran_erp.tables.text(value.content ?? "") : String(value);
};

iran_erp.tables.fit = function (wrapper, options) {
	const columns = options && options.columns;
	const data = (options && options.data) || [];
	if (!Array.isArray(columns) || !columns.length || options.layout === "ratio") return options;
	const T = iran_erp.tables;
	const rows = data.slice(0, T.SAMPLE_ROWS);
	const widths = columns.map((column, index) => {
		if (typeof column !== "object" || column === null) return null;
		if (column.iran_fixed_width) return column.width;
		let width = T.measure(__(column.name || column.label || column.content || ""), true);
		const key = column.id || column.fieldname;
		rows.forEach((row) => {
			let value;
			if (Array.isArray(row)) value = row[index];
			else if (row && typeof row === "object") value = row[key];
			const text = T.cell_text(column, value, row);
			let cell = T.measure(text, row && (row.bold || row.is_total_row));
			// Tree reports indent the first column by the row's level
			if (index === 0 && row && !Array.isArray(row) && row.indent) cell += row.indent * T.INDENT + 16;
			if (cell > width) width = cell;
		});
		// Link cells draw a little more than their text
		const fieldtype = column.fieldtype || (column.docfield && column.docfield.fieldtype);
		const extra = ["Link", "Dynamic Link"].includes(fieldtype) ? 18 : 0;
		return Math.round(Math.min(T.MAX_WIDTH, Math.max(T.MIN_WIDTH, width * T.SCALE + T.PADDING + extra)));
	});

	// Room on the page for the columns: the table's width less the row number and checkbox columns
	const available = (wrapper && wrapper.clientWidth ? wrapper.clientWidth : 0) - 90;
	const total = widths.reduce((sum, w) => sum + (w || 0), 0);
	const scale = available > 0 && total > 0 && total < available ? available / total : 1;

	options.columns = columns.map((column, i) => {
		if (widths[i] === null) return column;
		return { ...column, width: Math.floor(widths[i] * scale) };
	});
	return options;
};

iran_erp.tables.wrap = function (Base) {
	if (!Base || !Base.prototype || Base.prototype.iran_fitted) return Base;
	const proto = Base.prototype;

	// Every table is drawn through refresh: the constructor calls it with no arguments, lists in
	// report view call it again with the rows they load
	const refresh = proto.refresh;
	proto.refresh = function (data, columns) {
		const rows = data || this.options.data;
		const source = columns || this.options.columns;
		if (Array.isArray(rows) && rows.length && Array.isArray(source)) {
			const fitted = iran_erp.tables.fit(this.wrapper, {
				data: rows,
				columns: source,
				layout: this.options.layout,
			}).columns;
			if (columns) columns = fitted;
			else this.options.columns = fitted;
		}
		return refresh.call(this, data, columns);
	};
	proto.iran_fitted = true;

	// The row-number column is measured in the default font; Persian digits are a little wider,
	// so «10» showed as «0...»
	const holder = document.createElement("div");
	holder.style.cssText = "position:absolute;left:-9999px;top:0;width:200px;";
	try {
		document.body.appendChild(holder);
		const probe = new Base(holder, { columns: ["x"], data: [] });
		const Style = Object.getPrototypeOf(probe.style);
		if (!Style.iran_row_index) {
			const row_index_width = Style.getRowIndexColumnWidth;
			Style.getRowIndexColumnWidth = function () {
				return row_index_width.call(this) + 16;
			};
			Style.iran_row_index = true;
		}
		probe.destroy && probe.destroy();
	} catch (e) {
		// The row numbers keep the table's own width
	} finally {
		holder.remove();
	}
	return Base;
};

// The table class arrives with the report bundle, which loads only when a report is opened
(function () {
	for (const [owner, key] of [
		[window, "DataTable"],
		[frappe, "DataTable"],
	]) {
		let current = iran_erp.tables.wrap(owner[key]);
		Object.defineProperty(owner, key, {
			configurable: true,
			get: () => current,
			set: (value) => (current = iran_erp.tables.wrap(value)),
		});
	}
})();
