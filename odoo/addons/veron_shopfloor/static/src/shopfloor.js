/** The shop floor: work centers, their work orders as cards, Odoo's start/pause/finish buttons and a
 * live timer. Every change is made on the server (veron.shopfloor). */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { formatFloat } from "@web/core/utils/numbers";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MODEL = "veron.shopfloor";

export class Shopfloor extends Component {
    static template = "veron_shopfloor.Shopfloor";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ centers: [], center: null, workorders: [], quantities: {}, now: Date.now() });
        onWillStart(() => this.loadCenters());
        const timer = setInterval(() => (this.state.now = Date.now()), 1000);
        onWillUnmount(() => clearInterval(timer));
    }

    async loadCenters() {
        this.state.centers = await this.orm.call(MODEL, "workcenters", []);
        if (this.state.center && !this.state.centers.some((c) => c.id === this.state.center)) {
            this.state.center = null;
        }
        if (!this.state.center && this.state.centers.length) {
            this.state.center = this.state.centers[0].id;
        }
        await this.loadWorkorders();
    }

    async loadWorkorders() {
        this.state.workorders = this.state.center
            ? await this.orm.call(MODEL, "workorders", [this.state.center])
            : [];
    }

    async openCenter(id) {
        this.state.center = id;
        await this.loadWorkorders();
    }

    async act(workorder, what) {
        const quantity = what === "done" ? this.state.quantities[workorder.id] ?? workorder.producing : undefined;
        const result = await this.orm.call(MODEL, "act", [workorder.id, what, quantity]);
        this.state.workorders = result.workorders;
        if (result.message) {
            this.notification.add(result.message, { type: "success" });
        }
        if (result.finish) {
            await this.finishProduction(result.finish.id);
        }
        await this.loadCenters();
    }

    async finishProduction(productionId) {
        const result = await this.orm.call(MODEL, "finish_production", [productionId]);
        if (result.action) {
            // Odoo asks first (components consumed differently, a backorder...)
            await this.action.doAction(result.action, { onClose: () => this.loadCenters() });
        } else if (result.message) {
            this.notification.add(result.message, { type: "success" });
        }
    }

    async scrap(workorder) {
        const action = await this.orm.call(MODEL, "scrap", [workorder.id]);
        await this.action.doAction(action, { onClose: () => this.loadWorkorders() });
    }

    setQuantity(workorder, ev) {
        this.state.quantities[workorder.id] = parseFloat(ev.target.value) || 0;
    }

    qty(value) {
        return formatFloat(value, { digits: [16, 3] }).replace(/\.?0+$/, "") || "0";
    }

    /** hh:mm:ss worked, live while it runs */
    elapsed(workorder) {
        let minutes = workorder.duration;
        if (workorder.running_since) {
            minutes += (this.state.now - deserializeDateTime(workorder.running_since.replace("T", " ")).toMillis()) / 60000;
        }
        const seconds = Math.max(Math.round(minutes * 60), 0);
        const pad = (n) => String(n).padStart(2, "0");
        return `${pad(Math.floor(seconds / 3600))}:${pad(Math.floor((seconds % 3600) / 60))}:${pad(seconds % 60)}`;
    }

    expected(workorder) {
        const minutes = Math.round(workorder.expected);
        return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
    }
}

registry.category("actions").add("veron_shopfloor.app", Shopfloor);
