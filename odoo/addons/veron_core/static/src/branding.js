/** ERP-VERON in the window title; the user menu without Odoo's documentation, support and account. */
import { registry } from "@web/core/registry";

for (const item of ["documentation", "support", "odoo_account"]) {
    registry.category("user_menuitems").remove(item);
}

registry.category("services").add("veron_title", {
    dependencies: ["title"],
    start(env, { title }) {
        title.setParts({ zopenerp: "ERP-VERON" });
    },
});
