import { Extension } from "@tiptap/react";
import { TextSelection } from "@tiptap/pm/state";
import type { Node as PMNode, ResolvedPos } from "@tiptap/pm/model";

const ITEM_TYPES = new Set(["listItem", "taskItem"]);

function itemDepth($from: ResolvedPos): number | null {
  for (let d = $from.depth; d > 0; d--) if (ITEM_TYPES.has($from.node(d).type.name)) return d;
  return null;
}

/**
 * Alt+↑ / Alt+↓ move the current list item (bullet, numbered or checklist) past its sibling.
 * Nested items move within their own list; the caret keeps its offset inside the item.
 */
export const ListItemMove = Extension.create({
  name: "listItemMove",

  addKeyboardShortcuts() {
    const move = (dir: -1 | 1) => () =>
      this.editor.commands.command(({ tr, dispatch, state }) => {
        const { $from } = state.selection;
        const depth = itemDepth($from);
        if (depth === null) return false;
        const parent = $from.node(depth - 1);
        const index = $from.index(depth - 1);
        const target = index + dir;
        if (target < 0 || target >= parent.childCount) return false;
        const node: PMNode = $from.node(depth);
        const sibling = parent.child(target);
        const start = $from.before(depth);
        const end = $from.after(depth);
        const offset = $from.pos - start;
        if (dispatch) {
          if (dir === -1) {
            const sibStart = start - sibling.nodeSize;
            tr.delete(start, end).insert(sibStart, node);
            tr.setSelection(TextSelection.create(tr.doc, sibStart + offset));
          } else {
            tr.insert(end + sibling.nodeSize, node).delete(start, end);
            tr.setSelection(TextSelection.create(tr.doc, start + sibling.nodeSize + offset));
          }
          tr.scrollIntoView();
        }
        return true;
      });
    return { "Alt-ArrowUp": move(-1), "Alt-ArrowDown": move(1) };
  },
});
