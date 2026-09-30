import { Extension } from "@tiptap/react";
import { Plugin, PluginKey, type EditorState } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

/**
 * Remembers the range an AI edit is working on. While a suggestion is pending the range stays
 * highlighted, and is mapped through every other change (typing elsewhere, remote refreshes), so
 * "Accept" replaces exactly the text the suggestion was made for — or refuses if it's gone.
 */

export interface AIEditTarget {
  from: number;
  to: number;
  phase: "working" | "preview";
}

export const aiEditTargetKey = new PluginKey<AIEditTarget | null>("aiEditTarget");

export function getAIEditTarget(state: EditorState): AIEditTarget | null {
  return aiEditTargetKey.getState(state) ?? null;
}

export const AIEditTargetExtension = Extension.create({
  name: "aiEditTarget",
  addProseMirrorPlugins() {
    return [
      new Plugin<AIEditTarget | null>({
        key: aiEditTargetKey,
        state: {
          init: () => null,
          apply(tr, value) {
            const meta = tr.getMeta(aiEditTargetKey) as AIEditTarget | null | undefined;
            if (meta !== undefined) return meta;
            if (!value || !tr.docChanged) return value;
            const from = tr.mapping.map(value.from, 1);
            const to = tr.mapping.map(value.to, -1);
            return to > from ? { ...value, from, to } : null;
          },
        },
        props: {
          decorations(state) {
            const target = aiEditTargetKey.getState(state);
            if (!target) return null;
            return DecorationSet.create(state.doc, [
              Decoration.inline(target.from, target.to, { class: `ai-edit-target ai-edit-${target.phase}` }),
            ]);
          },
        },
      }),
    ];
  },
});
