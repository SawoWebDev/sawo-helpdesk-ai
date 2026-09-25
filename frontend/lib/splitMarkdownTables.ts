export type MarkdownBlock =
  | { type: "text"; content: string }
  | { type: "table"; content: string };

// A GFM table's second line is its delimiter row: pipes, dashes, optional
// alignment colons and nothing else (e.g. "|:---|---:|---|").
const DELIMITER_ROW = /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/;

function isTableRow(line: string): boolean {
  return line.includes("|") && line.trim() !== "";
}

/**
 * Splits an assistant reply into text blocks and GFM table blocks, in order.
 *
 * Tables are pulled out so they can be rendered as their own full-width card
 * instead of inside the chat bubble, which is capped at 80% of an already
 * narrow column — too tight for a spec table's model codes to fit on one line.
 * Everything that isn't a table is left untouched and still rendered as
 * ordinary markdown inside a bubble.
 */
export function splitMarkdownTables(text: string): MarkdownBlock[] {
  const lines = text.split("\n");
  const blocks: MarkdownBlock[] = [];
  let buffer: string[] = [];

  function flushText() {
    // Blank-only buffers would otherwise render as an empty bubble between
    // a heading and the table that follows it.
    if (buffer.join("").trim() !== "") blocks.push({ type: "text", content: buffer.join("\n") });
    buffer = [];
  }

  for (let i = 0; i < lines.length; i++) {
    const startsTable =
      isTableRow(lines[i]) && i + 1 < lines.length && DELIMITER_ROW.test(lines[i + 1]) && lines[i + 1].includes("|");

    if (!startsTable) {
      buffer.push(lines[i]);
      continue;
    }

    flushText();
    const tableLines: string[] = [lines[i], lines[i + 1]];
    let j = i + 2;
    while (j < lines.length && isTableRow(lines[j])) {
      tableLines.push(lines[j]);
      j++;
    }
    blocks.push({ type: "table", content: tableLines.join("\n") });
    i = j - 1;
  }

  flushText();
  return blocks;
}

export function hasMarkdownTable(text: string): boolean {
  return splitMarkdownTables(text).some((b) => b.type === "table");
}
