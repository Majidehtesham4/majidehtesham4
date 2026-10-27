/**
 * Leaving a form whose changes cannot be saved, because a required field is empty: Odoo only shows
 * «required fields missing» and keeps the form, which may be hidden behind the apps page. Here the
 * person is asked: back to the form, with the empty fields marked, or leave without those changes.
 *
 * Odoo also saves the open form when the browser tab is hidden (another tab, another window, a
 * screenshot). A form with nothing typed, or with a required field still empty, then showed the same
 * message for nothing; it is now left as it is, unsaved, until the person comes back to it.
 */
import { onMounted } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.veronMenu = useService("menu");
        // The app of the form, shown again in the navbar when the person goes back to it
        onMounted(() => (this.veronApp = this.veronMenu.getCurrentApp()));
    },

    beforeVisibilityChange() {
        const record = this.model.root;
        if (document.visibilityState === "hidden" && (!record.dirty || !record._checkValidity({ silent: true }))) {
            return;
        }
        return super.beforeVisibilityChange(...arguments);
    },

    async beforeLeave(options = {}) {
        const record = this.model.root;
        if (!record.dirty || options.forceLeave || (await record.checkValidity())) {
            return super.beforeLeave(...arguments);
        }
        // Close the apps page, so the form and its marked fields are seen
        this.env.bus.trigger("ACTION_MANAGER:UI-UPDATED");
        const leave = await new Promise((resolve) => {
            this.dialogService.add(
                ConfirmationDialog,
                {
                    title: _t("This form is not saved"),
                    body: _t(
                        "Some fields of this form are empty or not valid, so its changes cannot be saved. Go back to the form and fill the fields marked in red, or leave it without these changes."
                    ),
                    confirmLabel: _t("Back to the Form"),
                    confirm: () => resolve(false),
                    cancelLabel: _t("Leave Without Saving"),
                    cancel: () => resolve(true),
                },
                { onClose: () => resolve(false) }
            );
        });
        if (leave) {
            await record.discard();
        } else if (this.veronApp) {
            this.veronMenu.setCurrentMenu(this.veronApp);
        }
        return leave;
    },
});
