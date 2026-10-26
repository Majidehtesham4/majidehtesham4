/** Odoo's sample data, shown in an empty view, in Persian: names and texts rather than Latin words. */
import { registry } from "@web/core/registry";
import { SampleServer } from "@web/model/sample_server";
import * as jalali from "./jalali/jalali";

// After the localization service, which sets the user's language
registry.category("services").add("veron_sample_data", {
    dependencies: ["localization"],
    start() {
        if (!jalali.isActive()) {
            return;
        }
        SampleServer.SAMPLE_TEXTS = ["نمونه‌ی اول", "نمونه‌ی دوم", "نمونه‌ی سوم", "نمونه‌ی چهارم", "نمونه‌ی پنجم"];
        SampleServer.SAMPLE_PEOPLE = ["علی رضایی", "مریم احمدی", "حسین کریمی", "زهرا موسوی", "رضا محمدی"];
        SampleServer.SAMPLE_COUNTRIES = ["ایران", "ترکیه", "امارات", "عراق", "ارمنستان"];
        SampleServer.DISPLAY_FORMATS = {
            ...SampleServer.DISPLAY_FORMATS,
            week: "'هفته' W yyyy",
            quarter: "'فصل' q yyyy",
        };
    },
});
