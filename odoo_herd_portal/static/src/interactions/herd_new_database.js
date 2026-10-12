import {registry} from "@web/core/registry";
import {Interaction} from "@web/public/interaction";

/**
 * /my/odoo/new: show the addresses the database will get, from the name
 * typed and the host suffix of the offer chosen.
 */
export class HerdNewDatabase extends Interaction {
    static selector = ".o_herd_new_database";
    dynamicContent = {
        "input[name='instance_name']": {"t-on-input": this.updateHosts},
        "input[name='template_id']": {"t-on-change": this.updateHosts},
    };

    start() {
        this.updateHosts();
    }

    updateHosts() {
        const offer = this.el.querySelector("input[name='template_id']:checked");
        const suffix = offer?.dataset.hostSuffix || "";
        const typed = this.el
            .querySelector("input[name='instance_name']")
            .value.trim()
            .toLowerCase();
        const name = typed || this.el.querySelector(".o_herd_name_example").textContent;
        this.el.querySelector(".o_herd_host").textContent = `${name}.${suffix}`;
        this.el.querySelector(".o_herd_staging_host").textContent =
            `${name}-staging.${suffix}`;
    }
}

registry
    .category("public.interactions")
    .add("odoo_herd_portal.new_database", HerdNewDatabase);
