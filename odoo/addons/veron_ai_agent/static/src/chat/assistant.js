/** The chat window of every page, as in Odoo: opened from the AI logo at the bottom corner of the page or from the
 * top bar. Each opening starts a new chat; the previous one may be resumed. The assistant knows the page the
 * person is on and answers with the person's own rights; what changes data waits for an approval. */
import { Component, useState } from "@odoo/owl";
import { router } from "@web/core/browser/router";
import { registry } from "@web/core/registry";
import { useBus } from "@web/core/utils/hooks";
import { session } from "@web/session";
import { AgentChat } from "./chat";

const TOGGLE = "VERON-AI:TOGGLE";
export const AI_LOGO = "/veron_ai_agent/static/description/icon.svg";

export class AssistantBox extends AgentChat {
    static template = "veron_ai_agent.AssistantBox";
    static props = {};

    setup() {
        super.setup();
        this.logo = AI_LOGO;
        this.box = useState({
            available: Boolean(session.veron_ai_assistant), open: false, minimized: false, loaded: false,
            banner: false,
        });
        useBus(this.env.bus, TOGGLE, () => this.toggle());
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
        if (this.box.open && this.box.minimized) {
            this.box.minimized = false;
            return;
        }
        this.box.open = !this.box.open;
        if (this.box.open) {
            await this.load();
            this.loadPrompts();
            setTimeout(() => {
                this.scroll();
                this.textarea.el?.focus();
            });
        }
    }

    async load() {
        if (this.box.loaded) {
            return;
        }
        const result = await this.orm.call("veron.ai.conversation", "veron_chat_assistant", []);
        if (!result) {
            this.box.available = false;
            this.box.open = false;
            return;
        }
        this.state.agents = await this.orm.call("veron.ai.agent", "veron_chat_agents_list", []);
        await this.switchAgent(result.agent_id, result);
        this.box.loaded = true;
    }

    async switchAgent(agentId, info = false) {
        const agent = this.state.agents.find((a) => a.id === agentId) || {};
        this.useAgent({ ...agent, name: agent.name || info?.name });
        this.useEngine(agentId, info ? info.ai : Boolean(agent.ai), info ? info.engine : agent.engine);
        if (!info) {
            const panel = await this.orm.call("veron.ai.agent", "veron_agent_panel", [agentId]);
            this.useEngine(agentId, panel.ai, panel.engine);
            this.state.webSearch = Boolean(panel.tools.find((t) => t.field === "use_web_search")?.value);
        }
        await this.newChat(agentId);
        this.box.banner = Boolean(this.state.previousId);
        this.loadPrompts();
    }

    async resume() {
        await this.openConversation(this.state.previousId);
        this.box.banner = false;
    }

    async clear() {
        await this.newChat();
        this.box.banner = Boolean(this.state.previousId);
    }

    expand() {
        this.action.doAction({
            type: "ir.actions.client", tag: "veron_ai_agent.chat", name: this.state.agentName,
            params: { agent_id: this.state.agentId, conversation_id: this.state.conversationId },
        });
        this.box.open = false;
    }

    close() {
        this.box.open = false;
        this.box.minimized = false;
    }
}

registry.category("main_components").add("veron_ai_agent.AssistantBox", { Component: AssistantBox });

/** The AI logo of the top bar: opens and closes the chat window */
export class AiSystray extends Component {
    static template = "veron_ai_agent.AiSystray";
    static props = {};

    setup() {
        this.logo = AI_LOGO;
        this.available = Boolean(session.veron_ai_assistant);
    }

    toggle() {
        this.env.bus.trigger(TOGGLE);
    }
}

registry.category("systray").add("veron_ai_agent.AiSystray", { Component: AiSystray }, { sequence: 95 });
