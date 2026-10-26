/** Spreadsheets and dashboards in Persian: list dates in Shamsi, «50,000 ریال» with its space. */
import { CurrencyPlugin } from "@spreadsheet/currency/plugins/currency";
import { ListDataSource } from "@spreadsheet/list/list_data_source";
import { deserializeDate, deserializeDateTime, formatDate, formatDateTime } from "@web/core/l10n/dates";
import { patch } from "@web/core/utils/patch";
import * as jalali from "@veron_core/jalali/jalali";

patch(ListDataSource.prototype, {
    // The spreadsheet turns a date into a number it then shows in Gregorian: the date as text instead
    _parseServerValue(field, value) {
        if (jalali.isActive() && value && field.type === "date") {
            return formatDate(deserializeDate(value));
        }
        if (jalali.isActive() && value && field.type === "datetime") {
            return formatDateTime(deserializeDateTime(value));
        }
        return super._parseServerValue(field, value);
    },
});

patch(CurrencyPlugin.prototype, {
    // The spreadsheet's format puts a symbol written after the amount right against it
    computeFormatFromCurrency(currency) {
        if (currency?.position !== "after") {
            return super.computeFormatFromCurrency(currency);
        }
        const decimals = currency.decimalPlaces ?? 2;
        return `#,##0${decimals ? "." + "0".repeat(decimals) : ""}[$ ${currency.symbol.trim()}]`;
    },
});
