/** The page of an agent, as in Odoo's AI app: the person's conversations with it, the chat, and the agent's panel
 * with its instructions, skills and tools, knowledge sources and triggers. A manager of the agents changes the
 * agent from the panel; everyone else reads it. */
import { useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { SelectCreateDialog } from "@web/views/view_dialogs/select_create_dialog";
import { AgentChat } from "./chat";

const KNOWLEDGE_ICONS = { file: "fa-file-text-o", link: "fa-globe", page: "fa-book", document: "fa-folder-open-o" };
const TRIGGER_ICONS = { schedule: "fa-clock-o", date: "fa-calendar", create: "fa-plus-square-o", update: "fa-pencil-square-o" };

export class AgentPage extends AgentChat {
    static template = "veron_ai_agent.AgentPage";

    setup() {
        super.setup();
        this.dialog = useService("dialog");
        this.page_ = useState({
            threads: [], search: "", unread: false, panel: false, tab: "instructions", editing: false, draft: "",
            searching: false,
        });
    }

    async start() {
        const params = this.props.action?.params || {};
        let agentId = params.agent_id;
        if (!agentId) {
            const agents = await this.orm.call("veron.ai.agent", "veron_chat_agents_list", []);
            agentId = agents[0]?.id;
        }
        if (!agentId) {
            return;
        }
        this.state.agentId = agentId;
        await this.loadPanel();
        if (params.conversation_id) {
            await this.openConversation(params.conversation_id);
        } else {
            await this.newChat(agentId);
        }
        await this.loadThreads();
    }

    get breadcrumbs() {
        const crumbs = this.env.config?.breadcrumbs || [];
        return crumbs.slice(0, -1);
    }

    get panel() {
        return this.page_.panel || {};
    }

    knowledgeIcon(item) {
        return KNOWLEDGE_ICONS[item.kind] || "fa-file-o";
    }

    triggerIcon(item) {
        return TRIGGER_ICONS[item.kind] || "fa-bolt";
    }

    async loadPanel() {
        const panel = await this.orm.call("veron.ai.agent", "veron_agent_panel", [this.state.agentId]);
        this.page_.panel = panel;
        this.useAgent(panel);
        this.useEngine(panel.id, panel.ai, panel.engine);
        this.state.webSearch = Boolean(panel.tools.find((t) => t.field === "use_web_search")?.value);
        this.loadPrompts();
    }

    async loadThreads() {
        this.page_.threads = await this.orm.call("veron.ai.conversation", "veron_chat_conversations",
            [this.state.agentId, this.page_.search, this.page_.unread]);
    }

    afterSend() {
        this.loadThreads();
    }

    async onNewChat() {
        await this.newChat();
        this.state.previousId = false;
        this.loadThreads();
    }

    async onOpenThread(thread) {
        await this.openConversation(thread.id);
        thread.unread = false;
    }

    onSearchThreads(ev) {
        this.page_.search = ev.target.value;
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => this.loadThreads(), 250);
    }

    setUnread(unread) {
        this.page_.unread = unread;
        this.loadThreads();
    }

    toggleSearch() {
        this.page_.searching = !this.page_.searching;
        if (!this.page_.searching) {
            this.state.filter = "";
        }
    }

    // --- the panel

    async write(values) {
        this.page_.panel = await this.orm.call("veron.ai.agent", "veron_agent_panel_write", [this.state.agentId, values]);
        this.state.webSearch = Boolean(this.page_.panel.tools.find((t) => t.field === "use_web_search")?.value);
    }

    editInstructions() {
        this.page_.draft = this.panel.instructions;
        this.page_.editing = true;
    }

    async saveInstructions() {
        await this.write({ instructions: this.page_.draft });
        this.page_.editing = false;
    }

    addSkill() {
        this.dialog.add(SelectCreateDialog, {
            resModel: "veron.ai.skill",
            title: _t("Add a Skill"),
            domain: [["id", "not in", this.panel.skills.map((s) => s.id)]],
            multiSelect: false,
            noCreate: true,
            onSelected: async ([id]) => id && (await this.write({ add_skill: id })),
        });
    }

    addSubagent() {
        this.dialog.add(SelectCreateDialog, {
            resModel: "veron.ai.agent",
            title: _t("Add a Subagent"),
            domain: [["id", "not in", [this.state.agentId, ...this.panel.subagents.map((s) => s.id)]]],
            multiSelect: false,
            noCreate: true,
            onSelected: async ([id]) => id && (await this.write({ add_subagent: id })),
        });
    }

    openRecord(model, id) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: model, res_id: id, views: [[false, "form"]] },
            { onClose: () => this.loadPanel() });
    }

    async openWizard(method) {
        const action = await this.orm.call("veron.ai.agent", method, [[this.state.agentId]]);
        await this.action.doAction(action, { onClose: () => this.loadPanel() });
    }

    async toggleTrigger(trigger) {
        await this.orm.write("veron.ai.trigger", [trigger.id], { active: !trigger.active });
        await this.loadPanel();
    }

    async removeTrigger(trigger) {
        await this.orm.unlink("veron.ai.trigger", [trigger.id]);
        await this.loadPanel();
    }

    configure() {
        this.openRecord("veron.ai.agent", this.state.agentId);
    }

    async openRuns() {
        const action = await this.orm.call("veron.ai.agent", "action_open_runs", [[this.state.agentId]]);
        this.action.doAction(action);
    }
}

registry.category("actions").add("veron_ai_agent.chat", AgentPage);
