/**
 * Word-level diff for AI edit previews: which words were removed, kept or added.
 * Longest-common-subsequence over word + whitespace + punctuation tokens. Very long inputs fall
 * back to "all removed, all added" rather than doing quadratic work on the main thread.
 */

export type DiffPart = { type: "same" | "add" | "del"; text: string };

const MAX_CELLS = 1_500_000;

export function tokenize(text: string): string[] {
  return text.match(/\s+|[\p{L}\p{N}'’_-]+|[^\s\p{L}\p{N}]/gu) ?? [];
}

export function diffWords(before: string, after: string): DiffPart[] {
  if (before === after) return before ? [{ type: "same", text: before }] : [];
  const a = tokenize(before);
  const b = tokenize(after);
  if ((a.length + 1) * (b.length + 1) > MAX_CELLS) {
    return merge([
      ...(before ? [{ type: "del" as const, text: before }] : []),
      ...(after ? [{ type: "add" as const, text: after }] : []),
    ]);
  }
  // lcs[i][j] = LCS length of a[i:] and b[j:]
  const w = b.length + 1;
  const lcs = new Uint32Array((a.length + 1) * w);
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lcs[i * w + j] = a[i] === b[j] ? lcs[(i + 1) * w + j + 1]! + 1 : Math.max(lcs[(i + 1) * w + j]!, lcs[i * w + j + 1]!);
    }
  }
  const out: DiffPart[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      out.push({ type: "same", text: a[i]! });
      i++;
      j++;
    } else if (lcs[(i + 1) * w + j]! >= lcs[i * w + j + 1]!) {
      out.push({ type: "del", text: a[i++]! });
    } else {
      out.push({ type: "add", text: b[j++]! });
    }
  }
  while (i < a.length) out.push({ type: "del", text: a[i++]! });
  while (j < b.length) out.push({ type: "add", text: b[j++]! });
  return merge(group(out));
}

/**
 * Present each stretch of changes as "removed phrase, then added phrase" instead of
 * word-by-word interleaving. Whitespace between two changes belongs to both sides.
 */
function group(parts: DiffPart[]): DiffPart[] {
  const out: DiffPart[] = [];
  let del = "";
  let add = "";
  const flush = () => {
    if (del) out.push({ type: "del", text: del });
    if (add) out.push({ type: "add", text: add });
    del = add = "";
  };
  parts.forEach((p, k) => {
    if (p.type === "del") del += p.text;
    else if (p.type === "add") add += p.text;
    else if (!p.text.trim() && (del || add) && parts[k + 1] && parts[k + 1]!.type !== "same") {
      del += p.text;
      add += p.text;
    } else {
      flush();
      out.push(p);
    }
  });
  flush();
  return out;
}

function merge(parts: DiffPart[]): DiffPart[] {
  const out: DiffPart[] = [];
  for (const p of parts) {
    const last = out[out.length - 1];
    if (last && last.type === p.type) last.text += p.text;
    else out.push({ ...p });
  }
  return out;
}

export function changeStats(parts: DiffPart[]): { added: number; removed: number } {
  const words = (s: string) => (s.match(/[\p{L}\p{N}]+/gu) ?? []).length;
  return {
    added: parts.filter((p) => p.type === "add").reduce((n, p) => n + words(p.text), 0),
    removed: parts.filter((p) => p.type === "del").reduce((n, p) => n + words(p.text), 0),
  };
}
