/**
 * Shamsi dates everywhere in the web client for a user working in Persian: luxon formats in the persian
 * calendar, and reads a typed Shamsi date. What goes to the server, and every machine format with
 * dashes (yyyy-MM-dd), stays Gregorian.
 */
import { registry } from "@web/core/registry";
import { isActive, parse } from "./jalali";

const { DateTime, Settings } = luxon;

const toFormat = DateTime.prototype.toFormat;
DateTime.prototype.toFormat = function (format, options = {}) {
    if (typeof format === "string" && format.includes("-")) {
        options = { ...options, outputCalendar: "gregory", numberingSystem: "latn" };
    }
    return toFormat.call(this, format, options);
};

const fromFormat = DateTime.fromFormat;
DateTime.fromFormat = function (text, format, options = {}) {
    if (isActive() && typeof format === "string" && !format.includes("-")) {
        const date = parse(text, format, options);
        if (date) {
            return date;
        }
    }
    return fromFormat.call(DateTime, text, format, options);
};

// After the localization service, which sets the user's language on luxon
registry.category("services").add("veron_jalali", {
    dependencies: ["localization"],
    start() {
        if (isActive()) {
            Settings.defaultOutputCalendar = "persian";
            // Digits of dates as in amounts
            Settings.defaultNumberingSystem = "latn";
            // For the styles that only apply to Shamsi pages
            document.body.classList.add("o_veron_shamsi");
        }
    },
});
