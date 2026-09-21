"use client";

import { KeyboardEvent, forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import { Bold, Link2 } from "lucide-react";

export interface RichAnswerEditorHandle {
  getMarkdown: () => string;
}

function escapeHtml(text: string) {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Only bold and links round-trip through this editor — that's all the
// toolbar can produce, so that's all we need to parse back out.
function lineToHtml(line: string): string {
  let out = "";
  let i = 0;
  while (i < line.length) {
    const rest = line.slice(i);
    const boldMatch = /^\*\*(.+?)\*\*/.exec(rest);
    const linkMatch = /^\[([^\]]+)\]\((\S+?)\)/.exec(rest);
    if (boldMatch) {
      out += `<strong>${escapeHtml(boldMatch[1])}</strong>`;
      i += boldMatch[0].length;
    } else if (linkMatch) {
      out += `<a href="${escapeHtml(linkMatch[2])}">${escapeHtml(linkMatch[1])}</a>`;
      i += linkMatch[0].length;
    } else {
      out += escapeHtml(rest[0]);
      i += 1;
    }
  }
  return out;
}

function markdownToHtml(markdown: string): string {
  return markdown.split("\n").map(lineToHtml).join("<br>");
}

function nodeToMarkdown(node: ChildNode): string {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? "";
  const el = node as HTMLElement;
  if (el.tagName === "BR") return "\n";
  const inner = Array.from(el.childNodes).map(nodeToMarkdown).join("");
  if (el.tagName === "STRONG" || el.tagName === "B") return inner ? `**${inner}**` : "";
  if (el.tagName === "A") {
    const href = el.getAttribute("href") || "";
    return inner ? `[${inner}](${href})` : "";
  }
  // Browsers sometimes wrap pasted or newly-typed content in a block element
  // instead of using <br> — treat it as a line break rather than dropping it.
  if (el.tagName === "DIV" || el.tagName === "P") return `\n${inner}`;
  return inner;
}

function htmlToMarkdown(root: HTMLElement): string {
  return Array.from(root.childNodes)
    .map(nodeToMarkdown)
    .join("")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function findAncestorTag(container: HTMLElement, tag: string): HTMLElement | null {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0) return null;
  let node: Node | null = sel.getRangeAt(0).commonAncestorContainer;
  if (node.nodeType === Node.TEXT_NODE) node = node.parentNode;
  let el = node as HTMLElement | null;
  while (el && el !== container) {
    if (el.tagName === tag) return el;
    el = el.parentElement;
  }
  return null;
}

function unwrap(el: HTMLElement) {
  const parent = el.parentNode;
  if (!parent) return;
  while (el.firstChild) parent.insertBefore(el.firstChild, el);
  parent.removeChild(el);
}

function wrapSelection(tagName: string): HTMLElement | null {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0) return null;
  const range = sel.getRangeAt(0);
  if (range.collapsed) return null;
  const wrapper = document.createElement(tagName);
  try {
    range.surroundContents(wrapper);
  } catch {
    // Selection spans multiple sibling elements (e.g. crosses a bold run) —
    // surroundContents can't handle that, so move the whole fragment instead.
    const frag = range.extractContents();
    wrapper.appendChild(frag);
    range.insertNode(wrapper);
  }
  sel.removeAllRanges();
  const newRange = document.createRange();
  newRange.selectNodeContents(wrapper);
  sel.addRange(newRange);
  return wrapper;
}

const RichAnswerEditor = forwardRef<RichAnswerEditorHandle, { initialMarkdown: string }>(
  function RichAnswerEditor({ initialMarkdown }, ref) {
    const editorRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
      if (editorRef.current) {
        editorRef.current.innerHTML = markdownToHtml(initialMarkdown);
      }
      // Populate once from the value the form mounted with; this editor is
      // uncontrolled after that so typing doesn't fight React re-renders.
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useImperativeHandle(ref, () => ({
      getMarkdown: () => (editorRef.current ? htmlToMarkdown(editorRef.current) : ""),
    }));

    function handleBold() {
      const container = editorRef.current;
      if (!container) return;
      container.focus();
      const existing = findAncestorTag(container, "STRONG");
      if (existing) {
        unwrap(existing);
        return;
      }
      wrapSelection("strong");
    }

    function handleLink() {
      const container = editorRef.current;
      if (!container) return;
      container.focus();
      const existing = findAncestorTag(container, "A");
      if (existing) {
        const current = existing.getAttribute("href") || "";
        const next = window.prompt("Link URL (clear to remove the link)", current);
        if (next === null) return;
        if (!next.trim()) unwrap(existing);
        else existing.setAttribute("href", next.trim());
        return;
      }

      const sel = window.getSelection();
      if (!sel || sel.rangeCount === 0 || sel.getRangeAt(0).collapsed) {
        window.alert("Select some text first to turn it into a link.");
        return;
      }
      const url = window.prompt("Link URL", "https://");
      if (!url || !url.trim()) return;
      const anchor = wrapSelection("a");
      anchor?.setAttribute("href", url.trim());
    }

    function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
      if (e.key !== "Enter") return;
      e.preventDefault();
      const sel = window.getSelection();
      if (!sel || sel.rangeCount === 0) return;
      const range = sel.getRangeAt(0);
      range.deleteContents();
      const br = document.createElement("br");
      range.insertNode(br);
      range.setStartAfter(br);
      range.setEndAfter(br);
      sel.removeAllRanges();
      sel.addRange(range);
    }

    return (
      <div className="flex flex-col">
        <div className="flex items-center gap-1 rounded-t border border-b-0 border-slate-300 bg-slate-50 px-2 py-1 dark:border-white/15 dark:bg-white/10">
          <button
            type="button"
            onClick={handleBold}
            title="Bold"
            aria-label="Bold"
            className="rounded p-1.5 text-slate-600 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-white/10"
          >
            <Bold size={14} />
          </button>
          <button
            type="button"
            onClick={handleLink}
            title="Insert link — select linked text and click again to view or edit its URL"
            aria-label="Insert link"
            className="rounded p-1.5 text-slate-600 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-white/10"
          >
            <Link2 size={14} />
          </button>
        </div>
        <div
          ref={editorRef}
          contentEditable
          onKeyDown={handleKeyDown}
          suppressContentEditableWarning
          className="min-h-[8rem] rounded-b border border-slate-300 px-3 py-2 text-sm outline-none [&_a]:font-semibold [&_a]:text-inherit [&_a]:no-underline [&_strong]:font-semibold dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
        />
      </div>
    );
  }
);

export default RichAnswerEditor;
