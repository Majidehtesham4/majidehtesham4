/** The Shamsi (Jalali) calendar for luxon dates, read through the browser's own persian calendar (Intl). */

const { DateTime, Settings } = luxon;

export const MONTHS = [
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
];

const persian = new Intl.DateTimeFormat("en-US-u-ca-persian-nu-latn", {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    timeZone: "UTC",
});

/** Shamsi dates are shown when the user works in Persian. */
export function isActive() {
    return /^fa/i.test(Settings.defaultLocale || "");
}

/** {year, month, day} in Shamsi of the date's own (local) day */
export function toJalali(date) {
    const parts = {};
    for (const part of persian.formatToParts(new Date(Date.UTC(date.year, date.month - 1, date.day)))) {
        parts[part.type] = part.value;
    }
    return { year: parseInt(parts.year), month: parseInt(parts.month), day: parseInt(parts.day) };
}

const dayOfYear = (month, day) => (month <= 6 ? (month - 1) * 31 : 186 + (month - 7) * 30) + day - 1;

/** The Gregorian luxon date of a Shamsi day, at the start of the day; like: a date whose zone is kept */
export function fromJalali(year, month, day, like = null) {
    let date = DateTime.fromObject(
        { year: year + 621, month: 3, day: 22 },
        like ? { zone: like.zone, locale: like.locale } : {}
    );
    for (let i = 0; i < 4; i++) {
        const j = toJalali(date);
        const delta = (year - j.year) * 365 + dayOfYear(month, day) - dayOfYear(j.month, j.day);
        if (!delta) {
            break;
        }
        date = date.plus({ days: delta });
    }
    return date;
}

export function monthLength(year, month) {
    if (month <= 6) {
        return 31;
    }
    if (month <= 11) {
        return 30;
    }
    return toJalali(fromJalali(year + 1, 1, 1).minus({ days: 1 })).day;
}

export function startOfMonth(date) {
    return date.startOf("day").minus({ days: toJalali(date).day - 1 });
}

export function endOfMonth(date) {
    return addMonths(startOfMonth(date), 1).minus({ days: 1 }).endOf("day");
}

export function startOfYear(date) {
    const { year } = toJalali(date);
    return fromJalali(year, 1, 1, date);
}

/** The same day n Shamsi months later (the last day of the month when it is shorter), same time */
export function addMonths(date, n) {
    const j = toJalali(date);
    const total = j.year * 12 + (j.month - 1) + n;
    const year = Math.floor(total / 12);
    const month = (total % 12) + 1;
    const day = Math.min(j.day, monthLength(year, month));
    const { hour, minute, second, millisecond } = date;
    return fromJalali(year, month, day, date).set({ hour, minute, second, millisecond });
}

export function monthName(date) {
    return MONTHS[toJalali(date).month - 1];
}

/** «آبان ۱۴۰۵» */
export function monthTitle(date) {
    const { year, month } = toJalali(date);
    return `${MONTHS[month - 1]} ${year}`;
}

const DIGITS = { "۰": 0, "۱": 1, "۲": 2, "۳": 3, "۴": 4, "۵": 5, "۶": 6, "۷": 7, "۸": 8, "۹": 9 };
const ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩";

export function latinDigits(text) {
    return String(text).replace(/[۰-۹٠-٩]/g, (c) => (c in DIGITS ? DIGITS[c] : ARABIC_DIGITS.indexOf(c)));
}

/**
 * A date typed in Shamsi read with a luxon format of numbers only (yyyy/MM/dd HH:mm:ss and the like):
 * the luxon DateTime, or null when the text is not a Shamsi date in that format.
 */
export function parse(text, format, opts = {}) {
    const fields = [];
    let pattern = "";
    const tokens = format.match(/y+|M+|d+|H+|m+|s+|[^A-Za-z]+|[A-Za-z]+/g) || [];
    for (let i = 0; i < tokens.length; i++) {
        const token = tokens[i];
        const kind = token[0];
        if ("yMdHms".includes(kind)) {
            // Next to another number, a field has its full width; between separators, 1 or 2 digits
            const joined = i + 1 < tokens.length && /^[yMdHms]/.test(tokens[i + 1]);
            const width = kind === "y" ? token.length : joined ? 2 : 0;
            pattern += width ? `(\\d{${width}})` : "(\\d{1,2})";
            fields.push(kind);
        } else if (/[A-Za-z]/.test(token)) {
            return null; // month names, am/pm: not a Shamsi format of ours
        } else {
            pattern += "\\s*" + token.trim().replace(/[.*+?^${}()|[\]\\/]/g, "\\$&") + "\\s*";
        }
    }
    const match = new RegExp(`^\\s*${pattern}\\s*$`).exec(latinDigits(text));
    if (!match) {
        return null;
    }
    const value = { y: null, M: 1, d: 1, H: 0, m: 0, s: 0 };
    fields.forEach((field, i) => (value[field] = parseInt(match[i + 1])));
    if (value.y === null) {
        return null;
    }
    if (value.y < 100) {
        value.y += 1400;
    }
    if (value.y < 1200 || value.y > 1699 || value.M < 1 || value.M > 12) {
        return null;
    }
    if (value.d < 1 || value.d > monthLength(value.y, value.M)) {
        return null;
    }
    const zone = opts.zone && opts.zone !== "default" ? opts.zone : undefined;
    const day = fromJalali(value.y, value.M, value.d);
    return DateTime.fromObject(
        { year: day.year, month: day.month, day: day.day, hour: value.H, minute: value.m, second: value.s },
        zone ? { zone } : {}
    );
}

/** The week of the Shamsi year (the first week holds 1 Farvardin), weeks starting on weekStart (luxon: 6 = Saturday) */
export function week(date, weekStart = 6) {
    const yearStart = startOfYear(date);
    const offset = (yearStart.weekday - weekStart + 7) % 7;
    const days = Math.round(date.startOf("day").diff(yearStart.startOf("day"), "days").days);
    return Math.floor((days + offset) / 7) + 1;
}
