// Copyright 2026 XtremXpert
// License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

/* Drop files directly onto a directory card or row.

   The stock drop zone only works on file views, where the directory comes
   from the action domain. Here, on directory views, the directory is the
   record under the pointer: the closest element carrying a data-id. Files
   dropped on empty space are refused with a clear message instead of
   landing in a surprise location. */
import {onMounted, onWillUnmount} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";
import {DmsUploadError, uploadDmsFiles} from "@dms/js/upload.esm";
import {_t} from "@web/core/l10n/translation";

export function createDirectoryDropExtension() {
    return {
        setup() {
            super.setup(...arguments);
            this.http = useService("http");
            this.notification = useService("notification");
            this._dropElements = [];
            onMounted(() => this._bindDropZone());
            onWillUnmount(() => this._unbindDropZone());
        },

        _bindDropZone() {
            const el = this.el || document.querySelector(".o_content");
            if (!el) {
                return;
            }
            const over = this._onDragOver.bind(this);
            const leave = this._onDragLeave.bind(this);
            const drop = this._onDrop.bind(this);
            el.addEventListener("dragover", over);
            el.addEventListener("dragleave", leave);
            el.addEventListener("drop", drop);
            this._dropElements.push([el, over, leave, drop]);
        },

        _unbindDropZone() {
            for (const [el, over, leave, drop] of this._dropElements) {
                el.removeEventListener("dragover", over);
                el.removeEventListener("dragleave", leave);
                el.removeEventListener("drop", drop);
            }
            this._dropElements = [];
        },

        _directoryIdFromEvent(ev) {
            // The record under the pointer: kanban cards and list rows
            // both carry data-id.
            const target = ev.target.closest("[data-id]");
            if (!target) {
                return false;
            }
            const resId = parseInt(target.dataset.id, 10);
            return Number.isInteger(resId) ? resId : false;
        },

        _onDragOver(ev) {
            if (!ev.dataTransfer || !this._directoryIdFromEvent(ev)) {
                return; // Not over a record: let the browser show its own cursor.
            }
            ev.preventDefault();
            ev.stopPropagation();
            ev.dataTransfer.dropEffect = "copy";
        },

        _onDragLeave(ev) {
            ev.stopPropagation();
        },

        async _onDrop(ev) {
            const directoryId = this._directoryIdFromEvent(ev);
            if (!directoryId) {
                return; // Dropped on empty space: nothing sensible to do.
            }
            ev.preventDefault();
            ev.stopPropagation();
            const files = ev.dataTransfer ? [...ev.dataTransfer.files] : [];
            if (!files.length) {
                return;
            }
            try {
                const results = await uploadDmsFiles(this.http, directoryId, files);
                for (const result of results) {
                    if (result.error) {
                        this.notification.add(result.error, {type: "danger"});
                    }
                }
                if (this.model) {
                    await this.model.load();
                }
                this.notification.add(
                    _t("%s file(s) uploaded", files.length),
                    {type: "success"},
                );
            } catch (error) {
                if (error instanceof DmsUploadError) {
                    this.notification.add(error.message, {type: "danger"});
                } else {
                    throw error;
                }
            }
        },
    };
}
