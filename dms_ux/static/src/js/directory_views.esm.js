// Copyright 2026 XtremXpert
// License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

/* Directory views with per-record file drop: see directory_drop.esm. */
import {createDirectoryDropExtension} from "./directory_drop.esm";
import {KanbanController} from "@web/views/kanban/kanban_controller";
import {kanbanView} from "@web/views/kanban/kanban_view";
import {ListController} from "@web/views/list/list_controller";
import {listView} from "@web/views/list/list_view";
import {patch} from "@web/core/utils/patch";
import {registry} from "@web/core/registry";

export class DirectoryKanbanController extends KanbanController {}
export class DirectoryListController extends ListController {}
patch(DirectoryKanbanController.prototype, createDirectoryDropExtension());
patch(DirectoryListController.prototype, createDirectoryDropExtension());

export const DirectoryKanbanView = {
    ...kanbanView,
    Controller: DirectoryKanbanController,
};
export const DirectoryListView = {
    ...listView,
    Controller: DirectoryListController,
};

registry.category("views").add("directory_kanban", DirectoryKanbanView);
registry.category("views").add("directory_list", DirectoryListView);
