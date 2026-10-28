/** The chat box of every page: the assistant everyone may use, which knows the page the person is on. It
 * answers with the person's own rights; what changes data waits for an approval. */
import { onWillStart, useState } from "@odoo/owl";
import { router } from "@web/core/browser/router";
import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { AgentChat } from "./chat";

export class AssistantBox extends AgentChat {
    static template = "veron_ai_agent.AssistantBox";
    static props = {};

    setup() {
        super.setup();
        this.box = useState({ available: false, open: false, loaded: false, name: "" });
        onWillStart(() => {
            this.box.available = Boolean(session.veron_ai_assistant);
        });
    }

    async start() {
        // The chat page's start opens the first agent; the box opens its own assistant when first shown
    }

    get pageLabel() {
        const controller = this.action.currentController;
        return controller?.displayName || controller?.action?.name || "";
    }

    page() {
        const props = this.action.currentController?.props || {};
        const model = props.resModel || router.current.model;
        const resId = props.resId || router.current.resId;
        if (!model) {
            return false;
        }
        // The list as the person sees it: its title and the conditions of the action and of the search
        const domain = Array.isArray(props.domain) ? props.domain : [];
        return { model, res_id: Number.isInteger(resId) ? resId : 0, title: this.pageLabel, domain };
    }

    async toggle() {
        this.box.open = !this.box.open;
        // The page makes room for the panel instead of being covered by it
        document.body.classList.toggle("o_veron_assistant_docked", this.box.open);
        if (this.box.open && !this.box.loaded) {
            const result = await this.orm.call("veron.ai.conversation", "veron_chat_assistant", []);
            if (!result) {
                this.box.available = false;
                return;
            }
            this.box.loaded = true;
            this.box.name = result.name;
            Object.assign(this.state, {
                agentId: result.agent_id, conversationId: result.conversation_id, messages: result.messages, files: [],
            });
            this.useEngine(result.agent_id, result.ai, result.engine);
        }
        if (this.box.open) {
            setTimeout(() => this.scroll());
        }
    }

    async clear() {
        const result = await this.orm.call("veron.ai.conversation", "veron_chat_new", [this.state.agentId]);
        Object.assign(this.state, { conversationId: result.conversation_id, messages: [], files: [], text: "" });
    }
}

registry.category("main_components").add("veron_ai_agent.AssistantBox", { Component: AssistantBox });
