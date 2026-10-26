/**
 * OCA's timeline view (project timeline, staff planning) in Shamsi: vis-timeline draws its gridlines on
 * Gregorian days and months; every label here is the exact Shamsi date of its gridline («2 آبان 1405»,
 * «شنبه 2»), so none stands for a Gregorian month.
 */
import { TimelineRenderer } from "@web_timeline/views/timeline/timeline_renderer.esm";
import { patch } from "@web/core/utils/patch";
import * as jalali from "@veron_core/jalali/jalali";

const { DateTime } = luxon;

const dayOf = (moment) => DateTime.fromJSDate(moment.toDate());
const time = (date, seconds = false) => date.toFormat(seconds ? "HH:mm:ss" : "HH:mm");
const day = (date) => String(jalali.toJalali(date).day);
const dayMonth = (date) => {
    const j = jalali.toJalali(date);
    return `${j.day} ${jalali.MONTHS[j.month - 1]}`;
};
const fullDate = (date) => `${dayMonth(date)} ${jalali.toJalali(date).year}`;
const weekday = (date) => `${date.setLocale("fa").toFormat("cccc")} ${day(date)}`;

const MINOR = {
    millisecond: (d) => time(d, true),
    second: (d) => time(d, true),
    minute: time,
    hour: time,
    weekday,
    day,
    week: dayMonth,
    month: dayMonth,
    year: fullDate,
};
const MAJOR = {
    millisecond: fullDate,
    second: fullDate,
    minute: fullDate,
    hour: fullDate,
    weekday: fullDate,
    day: fullDate,
    week: fullDate,
    month: fullDate,
    year: () => "",
};

patch(TimelineRenderer.prototype, {
    init_timeline() {
        if (jalali.isActive()) {
            this.options.format = {
                minorLabels: (moment, scale) => (MINOR[scale] || fullDate)(dayOf(moment)),
                majorLabels: (moment, scale) => (MAJOR[scale] || fullDate)(dayOf(moment)),
            };
        }
        return super.init_timeline(...arguments);
    },
});
