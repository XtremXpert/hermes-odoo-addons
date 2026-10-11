import {Component, onMounted, onWillUnmount, proxy, t, useProps} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";
import {Thread} from "@mail/core/common/thread";
import {patch} from "@web/core/utils/patch";

export class HermesActivity extends Component {
    static template = "hermes_activity.Status";
    setup() {
        this.props = useProps({channelId: t.number()});
        this.orm = useService("orm");
        this.state = proxy({
            activity: null,
            now: Date.now(),
            unavailable: false,
            channelId: null,
        });
        this.alive = true;
        this.busy = false;
        onMounted(() => {
            this.refresh();
            this.timer = setInterval(() => this.refresh(), 3000);
        });
        onWillUnmount(() => {
            this.alive = false;
            clearInterval(this.timer);
        });
    }
    async refresh() {
        if (this.busy || !this.alive) return;
        const channelId = this.props.channelId;
        if (this.state.channelId !== channelId) {
            this.state.activity = null;
            this.state.unavailable = false;
            this.state.channelId = channelId;
        }
        this.busy = true;
        try {
            const activity = await this.orm.call("hermes.activity", "lire", [], {
                channel_id: channelId,
            });
            if (this.alive && this.props.channelId === channelId) {
                this.state.activity = activity || null;
                this.state.unavailable = false;
            }
        } catch {
            if (this.alive && this.props.channelId === channelId)
                this.state.unavailable = true;
        } finally {
            this.busy = false;
            if (this.alive) this.state.now = Date.now();
        }
    }
    get activity() {
        return this.state.channelId === this.props.channelId
            ? this.state.activity
            : null;
    }
    get running() {
        return ["working", "tool"].includes(this.activity?.state);
    }
    get stale() {
        return (
            this.running &&
            (this.state.unavailable ||
                this.state.now / 1000 - this.activity.updated_at > 90)
        );
    }
    get elapsed() {
        const end = this.running ? this.state.now / 1000 : this.activity.updated_at;
        const seconds = Math.max(0, Math.floor(end - this.activity.started_at));
        return seconds < 60
            ? `${seconds} s`
            : `${Math.floor(seconds / 60)} min ${seconds % 60} s`;
    }
    get steps() {
        return this.activity?.steps || [];
    }
    get hiddenSteps() {
        return Math.max(0, (this.activity?.step_count || 0) - this.steps.length);
    }
    stepDuration(step) {
        const end =
            step.ended_at ??
            (this.stale ? this.activity.updated_at : this.state.now / 1000);
        const seconds = Math.max(0, Math.floor(end - step.started_at));
        return seconds < 60
            ? `${seconds} s`
            : `${Math.floor(seconds / 60)} min ${seconds % 60} s`;
    }
}
patch(Thread, {components: {...Thread.components, HermesActivity}});
