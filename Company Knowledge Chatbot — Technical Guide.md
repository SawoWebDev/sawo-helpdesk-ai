# Company Knowledge Chatbot — Technical Guide

Oct 15, 2026 · @Rafael

## Overview

The goal: a company chatbot that answers any question about the company, its products and its SOPs in a few seconds, no matter how much data is loaded. The video's method gets there by never loading everything. It keeps the knowledge in organized files, maps how it connects, and routes each question to the 3–10 pages that matter.

The video's three parts map directly onto a company bot:


| Video (personal setup)                        | Company chatbot equivalent                                               | Job                                               |
| --------------------------------------------- | ------------------------------------------------------------------------ | ------------------------------------------------- |
| Obsidian vault (PARA folders, Markdown notes) | Company knowledge base: products, SOPs, policies, FAQs as Markdown files | **Memory** — where every fact lives              |
| Graphify (nodes, edges, communities)          | Knowledge graph + search index built from the knowledge base             | **Connections** — finds related facts fast       |
| ICM (CLAUDE.md routing table, project cards)  | Router + topic cards (company core card, product cards, SOP cards)       | **Direction** — tells the AI where to look first |
| "One home per fact" rule                      | Single source of truth per fact, with an owner                           | **Accuracy** — no conflicting answers            |

One difference matters. The video's setup is a personal Claude Code workflow where the AI walks files on a PC. A company bot serves many people at once, so the slow work (reading, graphing, indexing) must happen **ahead of time**, and the question-time work must be a fast lookup plus one AI call.

## Why not just load everything

Stuffing all company documents into every prompt fails on four counts, and they get worse as the company grows.

- **It doesn't fit.** A mid-size company's docs easily pass 1 million words. Even the largest context windows can't hold that reliably in one request.
- **Accuracy drops.** Models miss or blend details buried in very long inputs, especially in the middle. Fewer, relevant pages give sharper answers.
- **It's slow.** Time to first word grows with input size. Reading 2,000 pages per question means long waits.
- **It's expensive.** You pay per token read. Sending everything on every question multiplies cost by hundreds.

The fix is the video's core idea: **the AI should know where to look, not read everything.** Reading 5 pages instead of 2,000 is what makes answers both fast and accurate.

## Architecture at a glance

The system splits into slow work done ahead of time and a fast path at question time, where only one AI call happens.

&#91;embedded content: chatbot architecture · offline build + question-time path\]

The top band is the video's Obsidian + Graphify work, run as a scheduled job. The bottom band is the ICM routing plus the video's "no-AI script" that pulls related notes, followed by a single answer call.

## Layer 1: Knowledge base (Memory)

Store company knowledge as plain Markdown files in a Git repo or shared folder, one topic per file. Plain text means any tool can read it, any staff member can edit it, and every change is tracked. Obsidian works well as the editor.

### Folder structure

```
company-kb/
├── CLAUDE.md            ← routing table (Layer 3)
├── _schema/             ← templates + writing rules
├── 00-core/             ← company profile, mission, contacts, hours, locations
├── 10-products/         ← one folder per product line, one card per product
├── 20-sops/             ← one file per procedure, grouped by department
├── 30-policies/         ← HR, returns, warranty, pricing rules, compliance
├── 40-faqs/             ← real customer/staff questions with approved answers
├── 50-departments/      ← who owns what, escalation paths
├── 60-decisions/        ← why things are done a certain way (rationale)
├── 70-lessons/          ← "gotchas": known issues, past mistakes, workarounds
└── 99-archive/          ← retired products, old policies (excluded from answers)
```

### Front matter on every file

This metadata is what lets the system filter and route without reading the body.

```yaml
---
id: sop-refund-request
type: sop            # product | sop | policy | faq | decision | lesson | core
title: Processing a customer refund request
summary: Steps to approve and issue a refund within 7 days of purchase.
department: customer-service
owner: cs-lead
audience: internal   # public | internal | restricted
tags: [refunds, payments, customer-service]
related: ["[[policy-return-window]]", "[[product-warranty-terms]]"]
last_reviewed: 2026-09-01
status: active       # active | draft | archived
---
```

### Note templates

- **Product card:** what it is, who it's for, key specs, variants, common questions, links to price/stock source, related SOPs.
- **SOP:** purpose, when to use, numbered steps, who approves, exceptions, related policies.
- **Policy:** the rule in one sentence, details, effective date, exceptions, owner.
- **FAQ:** the question as people actually ask it (plus 2–3 alternate phrasings), the approved answer, source links.
- **Lesson/gotcha:** what went wrong, why, the fix. These are what make a bot feel experienced.

### One home per fact

Every fact lives in exactly one file; everything else links to it with `[[double brackets]]`. If the refund window is 7 days, it appears only in `policy-return-window.md`. The refund SOP links there instead of repeating "7 days." When the policy changes, one edit updates every answer.

**Live data does not go in notes.** Prices, stock levels, order status and customer records change daily. They stay in your system of record (ERP, POS, CRM) and the bot reads them live through a tool call. The note only says *where* that data lives.

## Layer 2: Knowledge graph + search index (Connections)

This layer is built **offline** (nightly or on every change), never at question time. It turns the knowledge base into two lookup structures the bot can query in milliseconds.

### A. The knowledge graph

The tool from the video is [Graphify](https://github.com/belinwu/graphify), an open-source skill for Claude Code and similar agents. It reads a folder, has AI sub-agents extract concepts and relationships from documents in parallel, and parses code locally with tree-sitter (no AI). It clusters the graph with the Leiden algorithm based on how densely things connect, not embeddings. Outputs land in `graphify-out/`: `graph.json` (queryable graph), `graph.html` (interactive map), and `GRAPH_REPORT.md` (key nodes and surprising connections). It supports incremental updates (`--update`) and auto-sync (`--watch`). ([source](https://claudelog.com/claude-code-mcps/graphify))

For a company, define the node and edge types up front:


| Node type            | Examples                                      |
| -------------------- | --------------------------------------------- |
| Product              | "Model X Water Purifier", "Premium Plan"      |
| SOP                  | "Refund request", "New hire onboarding"       |
| Policy               | "30-day return window", "Overtime policy"     |
| Department / Role    | "Customer Service", "Warehouse Lead"          |
| Concept / Term       | "Warranty claim", "Bulk discount"             |
| Decision / Rationale | "Why we stopped COD in Region 4"              |
| Lesson / Gotcha      | "Model X filter fails if installed backwards" |


| Edge type                 | Meaning                                       |
| ------------------------- | --------------------------------------------- |
| `governed_by`             | SOP or product → the policy that controls it |
| `owned_by`                | Anything → the department/role responsible   |
| `requires` / `depends_on` | Step or product → prerequisite               |
| `part_of`                 | Variant → product line; step → SOP          |
| `rationale_for`           | Decision → the thing it explains             |
| `known_issue`             | Lesson → the product/SOP it affects          |
| `related_to`              | Weaker general link                           |

Keep the video's trust labels on every edge: **EXTRACTED** (literally stated in a file), **INFERRED** (AI-guessed, with confidence score), **AMBIGUOUS**. For a company bot, policy and pricing answers should rely only on EXTRACTED edges.

### B. The search index (hybrid)

The graph needs an entry point: which nodes match the question? Build two indexes over the files, split into sections of roughly 200–500 words:

1. **Keyword index (BM25):** catches exact terms like product codes, SKUs, form names ("Form HR-07").
2. **Vector index (embeddings):** catches meaning when words differ ("money back" → refund policy).

At question time, both run, results merge, and the top matches become starting nodes for the graph walk. This combination is often called **GraphRAG**: search finds the door, the graph finds the rooms behind it.

### Production note

Graphify is designed for an AI coding assistant working on a folder, not as a web service. Two practical paths: use Graphify to build `graph.json` and load it into your backend (e.g., with NetworkX, which Graphify itself uses), or write a small custom extraction pipeline that writes nodes and edges straight into your database. The design above stays the same either way.

## Layer 3: Routing with ICM (Direction)

ICM (Interpretable Context Methodology, by Jake Van Clief) treats the folder structure itself as the AI's instructions. Its key principle for us is layered context loading: the AI loads only what the current step needs. ([source](https://arxiv.org/pdf/2603.16021))

In the chatbot, this becomes three things.

### 1. The routing table (CLAUDE.md / system prompt)

A short file, always loaded, that maps question types to where answers live:

```markdown
# Company Assistant — Routing Table

You answer questions for [Company] staff and customers.
Answer ONLY from the context provided. If it's not there, say so and name who to ask.
Always cite the source file.

| If the question is about...      | Go to                    | Also check            |
|----------------------------------|--------------------------|-----------------------|
| Company info, hours, contacts    | 00-core/company-card.md  | —                     |
| A product (features, use, specs) | 10-products/<line>/      | related SOPs, lessons |
| Price, stock, order status       | TOOL: erp_lookup         | product card          |
| "How do I..." (a process)        | 20-sops/<dept>/          | linked policies       |
| Rules, eligibility, HR           | 30-policies/             | decisions (why)       |
| Who handles X / escalation       | 50-departments/          | —                     |
```

### 2. Cards (short pointers, not stories)

Like the video's project cards: every product line, department and major process gets a short card with status and a link table. The card never holds the full content; it points to where it lives.

```markdown
# Card: Water Purifier Line
status: active · owner: product-team · last_update: 2026-09-20
summary: 3 models (X, X-Pro, Mini). X-Pro is the best seller.

| What                | Where                                   |
|---------------------|-----------------------------------------|
| Product details     | 10-products/purifiers/model-x.md, ...   |
| Live price & stock  | TOOL: erp_lookup(sku)                   |
| Install SOP         | 20-sops/service/purifier-install.md     |
| Warranty policy     | 30-policies/warranty-purifiers.md       |
| Known issues        | 70-lessons/purifier-filter-backwards.md |
```

### 3. The intent router

Before retrieval, classify the question: which route, and does it need live data? Use simple keyword rules for obvious cases (an order number pattern → order lookup) and a small, fast model for the rest. This step should take well under a second. The route narrows search to one or two folders, which makes retrieval both faster and more accurate.

## Query pipeline: what happens when someone asks

Everything before the final AI call is plain code and database lookups, so the user sees the first words in about 1–2 seconds. This mirrors the video's "small script, no AI" hook that pulls related notes before Claude answers.

Example question: *"Can a customer return a Model X purifier after 20 days if the filter is damaged?"*

1. **Check the answer cache.** If this exact (or near-identical) question was answered recently and its sources haven't changed, return the cached answer instantly.
2. **Route.** Rules + small model classify it: product + policy question, no live data needed. Search is limited to `10-products/purifiers/`, `30-policies/`, `70-lessons/`.
3. **Hybrid search.** Keyword + vector search finds starting nodes: `model-x.md`, `policy-return-window.md`.
4. **Graph walk (1–2 hops).** From those nodes, follow edges: Model X → `governed_by` → warranty policy; Model X → `known_issue` → filter-installed-backwards lesson. This finds the warranty rule that keyword search alone would miss.
5. **Permission filter.** Drop anything above the user's access level (a customer never sees `internal` notes).
6. **Assemble context.** Take the top 5–10 sections, about 3,000–8,000 tokens. Put the always-loaded routing table and company core card first (cached).
7. **Live data (only if needed).** If the route said price/stock/order, call the ERP tool in parallel with steps 3–5.
8. **Generate and stream.** One call to the main model, answer streamed word by word, with source citations.
9. **Log.** Save question, sources used, answer and user feedback for review.


| Step                         | Typical target time                | Uses AI?                           |
| ---------------------------- | ---------------------------------- | ---------------------------------- |
| Cache check                  | < 50 ms                            | No                                 |
| Route                        | 50–400 ms                         | Rules first, small model if needed |
| Hybrid search                | 50–200 ms                         | Embedding of the question only     |
| Graph walk                   | < 50 ms                            | No                                 |
| Permission filter + assemble | < 50 ms                            | No                                 |
| Live data tool               | 100–800 ms (parallel)             | No                                 |
| First streamed words         | \~0.5–1.5 s after the call starts | Yes (main model)                   |

These are typical design targets, not measurements; actual numbers depend on your hosting and model choice. Measure them in Phase 2 of the roadmap.

## Making it instant: speed techniques

Speed comes from doing work before the question arrives and keeping the question-time context small. In order of impact:

1. **Precompute everything.** Extraction, graph building, embeddings and summaries run offline. Question time is lookups only.
2. **Small context, always.** Cap retrieved context (e.g., 8,000 tokens). More context is slower, costlier and often less accurate.
3. **Prompt caching.** The routing table, rules and company core card are identical on every request. Put them first in the prompt and mark them cacheable (the Claude API supports prompt caching). Repeat reads become faster and cheaper.
4. **Answer cache for top questions.** In most companies a few dozen questions make up a large share of traffic. Cache their answers and invalidate when a source file changes.
5. **Pre-written FAQ answers.** For the most common questions, store an approved answer in `40-faqs/`. Retrieval hits it first, so the model mostly rephrases rather than reasons.
6. **Tiered models.** A small fast model for routing; the stronger model only for the final answer. Simple lookups ("What are your hours?") can be answered by the small model alone.
7. **Parallelize.** Run search, graph walk and live-data tool calls at the same time.
8. **Stream the answer.** Users perceive speed by the first word, not the last.
9. **Keep indexes hot.** Load the graph into memory at server start; keep the vector index in the same region as the server.
10. **Incremental updates.** Re-process only changed files, like the video (82 new notes in \~13 minutes). Never rebuild everything on each edit.

## Accuracy, permissions and keeping it updated

### Accuracy

- **Answer only from retrieved context.** The system prompt says: if it's not in the provided files, say "I don't have that information" and name the owner to ask. A confident wrong answer is worse than none.
- **Cite sources** on every answer (file title + link) so staff can verify.
- **Trust labels.** Policy, price and legal answers use only EXTRACTED facts. INFERRED connections can suggest "you may also want to check..." but never state rules.
- **Freshness.** Show `last_reviewed` when it's older than, say, 6 months, and flag it to the owner.
- **Test set.** Keep 50–100 real questions with correct answers. Run them after every major change and track the pass rate.

### Permissions

- Tag every file with `audience` (public / internal / restricted) and optionally `department`.
- Filter by the user's role **before** retrieval, not after generation. The model should never see content the user can't see.
- Run separate deployments if needed: a public website bot (public files only) and an internal staff bot.
- Never put secrets (passwords, API keys, salary data) in the knowledge base.

### Keeping it updated

- **Owners per folder.** Each department owns its files and reviews them on a schedule.
- **Change triggers rebuild.** A Git commit or file save triggers incremental re-indexing of changed files only (Graphify offers `--update` and a commit hook for this).
- **Learn from gaps.** Log every "I don't know" and low-rated answer. Weekly, owners turn the top gaps into new FAQ or SOP files.
- **Session notes, company version.** As in the video's "save progress" habit, after a project or incident, have the AI draft a lesson note (what happened, what failed, what was decided) for the owner to approve into `70-lessons/` or `60-decisions/`.

## Tech stack options and build roadmap

Start with Option A to prove the knowledge base works, then move to Option B for a real multi-user bot. The knowledge base you write in Phase 1 carries over unchanged.


| Option                    | What it is                                                                                                                                                                                     | Best for                                         | Effort      |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ | ----------- |
| **A. Video setup, as-is** | Knowledge base folder + Claude Code + Graphify + CLAUDE.md routing, exactly like the video                                                                                                     | Internal power users, testing the knowledge base | Days        |
| **B. Custom web chatbot** | Backend (Python or Node) + Postgres with vector search (e.g., Supabase + pgvector) + graph tables or graph.json in memory + Claude API with prompt caching + web/chat front end (e.g., Vercel) | Staff portal, customer website bot, many users   | Weeks       |
| **C. Packaged platform**  | A hosted RAG/chatbot product that indexes your files                                                                                                                                           | Fast launch, less control over routing and graph | Days–weeks |

For live data in Option B, connect the bot to your ERP/CRM through a read-only API or tool (e.g., if you run Odoo: product lookup, customer lookup, order status). Read-only first; any write action (creating orders, refunds) needs separate review and approval.

### Roadmap

1. **Phase 1 — Knowledge base (weeks 1–3).** Create folders and templates. Write the company core card. Convert the top 20 SOPs, all active product cards, key policies, and the 50 most-asked questions. Apply one home per fact. Assign owners.
2. **Phase 2 — Prototype (week 4).** Option A: run Graphify on the folder, write CLAUDE.md and cards, and test with 50 real questions. Fix gaps in the notes, not in the prompt.
3. **Phase 3 — Build the service (weeks 5–8).** Option B: indexing pipeline (chunk, embed, extract graph), hybrid search, graph walk, router, permission filter, prompt caching, streaming chat UI, logging.
4. **Phase 4 — Live data (weeks 8–9).** Read-only ERP/CRM tools for price, stock, order status.
5. **Phase 5 — Pilot (weeks 10–11).** One department uses it daily. Track accuracy on the test set, response time, and "I don't know" rate.
6. **Phase 6 — Rollout and upkeep (week 12+).** Expand to all staff, then a public version with public-only files. Weekly gap review; quarterly owner reviews.

Week counts assume one or two developers plus department owners writing content; content writing is usually the slowest part.

## Pitfalls and checklist

### Common pitfalls

- **Dumping PDFs as-is.** Scanned manuals and 80-page PDFs retrieve poorly. Convert key content into clean, one-topic Markdown files.
- **Duplicate facts.** The same price or policy in three files guarantees a wrong answer someday. Link, don't copy.
- **Live data in notes.** Prices and stock typed into notes go stale. Read them from the system of record.
- **No owner.** Files without an owner rot. Every folder needs a named person.
- **Fixing answers in the prompt.** When the bot is wrong, fix the source file. Prompt patches pile up and conflict.
- **Trusting inferred links for rules.** AI-guessed connections are hints, not policy.
- **Skipping the test set.** Without one, every change is a guess.

### Launch checklist

- [ ]  Folder structure and templates created
- [ ]  Company core card written
- [ ]  Product cards for all active products
- [ ]  Top SOPs and policies converted
- [ ]  50+ FAQs with approved answers
- [ ]  Front matter on every file (type, owner, audience, last\_reviewed)
- [ ]  No fact stored in two places
- [ ]  Routing table and cards written
- [ ]  Graph + hybrid index built, incremental updates working
- [ ]  Permission filter tested with public and internal users
- [ ]  Live data tools read-only
- [ ]  Test set of 50–100 questions passing
- [ ]  Logging and weekly gap review in place

## Sources

- [Graphify on GitHub](https://github.com/belinwu/graphify) — install, outputs, Claude Code hook, Leiden clustering
- [Graphify on ClaudeLog](https://claudelog.com/claude-code-mcps/graphify) — tree-sitter parsing, no vector store, incremental updates
- [Graphify overview (The Menon Lab)](https://themenonlab.blog/blog/graphify-knowledge-graph-claude-code-karpathy) — parallel subagents, graph as index
- [Interpretable Context Methodology paper (arXiv 2603.16021)](https://arxiv.org/pdf/2603.16021) — ICM design principles, layered context loading
- [ICM summary (Clief Notes)](https://www.skool.com/cliefnotes/when-i-need-a-reminder-of-what-were-doing) — folder structure as architecture, stage contracts
- Source video transcript (Taglish), provided by the user



IDEA:


**How an AI Can “Know” 1,000+ Notes Without Reading All of Them**
*(The 3-part setup: Obsidian + Graphify + ICM)*

**The problem it solves**
The creator has over 1,000 notes, more than 1 million words (about 2,000 pages). Claude and ChatGPT now have “memory,” but it’s only a short summary; it doesn’t hold the full history of every project. And even the biggest AI can’t reliably take in 2,000 pages in one chat. When an AI reads too much at once, it gets **less accurate, slower, and more expensive**. The better approach: make the AI know **exactly which few notes to read** for each question.

The setup has three parts, each with one job:

* **Obsidian = Memory** (where the knowledge lives)
* **Graphify = Connections** (how the knowledge is linked)
* **ICM = Direction** (tells the AI where to look)

---

**PART 1 — OBSIDIAN (Memory)**

Obsidian is just a folder on the PC full of plain text files (Markdown, .md). Nothing special or locked in.

It’s organized into 5 folders using the **PARA** method:

1. **Inbox** – new, unsorted notes
2. **Projects** – active work (82 projects, each with its own folder)
3. **Areas** – ongoing responsibilities
4. **Resources** – reference knowledge
5. **Archive** – finished or inactive items

Inside each project folder:

* One **hub note** (the main overview of the project)
* **Dated session notes**. Whenever he tells Claude “save progress,” Claude writes the note itself: what was done, what went wrong, and what was decided.

Inside Resources is a **Zettelkasten**: 300+ small notes, each holding **one idea only** (example: “one home per fact”).

Every note has:

* **Front matter** at the top: type, tags, date, and a short summary
* **Links** to other notes using [[double brackets]] — about 5,000 links total

**The limitation:** those links only capture connections *he* noticed. Connections he never spotted are missing. That’s where Part 2 comes in.

---

**PART 2 — GRAPHIFY (Connections)**

Graphify turns all the notes into a **knowledge graph** (a map of things and how they relate).

**How it builds the graph:**

1. It splits the notes into chunks of about 22 notes each.
2. Multiple AI agents read the chunks **at the same time** (parallel).
3. Code files are handled by a parser — **no AI needed** for those.
4. Every important “thing” becomes a **node**: a project, a tool, a decision, the reason behind a decision, or a “gotcha” (a mistake or lesson learned). Result: almost **9,000 nodes**.
5. Every relationship between two nodes becomes an **edge**: “references,” “rationale for,” “depends on,” “related to.” Result: over **13,000 edges**.

**Every edge is labeled by how trustworthy it is:**

* **EXTRACTED** – literally written in a note (fact)
* **INFERRED** – the AI guessed it, with a confidence score
* **AMBIGUOUS** – unclear
  About 90% of his edges are EXTRACTED, so he always knows what’s fact and what’s a guess.

**Grouping (Leiden algorithm):** It clusters nodes that are often connected into **communities** (e.g., everything about GoHighLevel together, everything about videos together). He has 200+ communities. When a link appears between two communities that are normally far apart, that’s a **“surprising connection”** — something he’d never have noticed himself.

**Output — 3 files** (saved *outside* the notes folder so notes stay clean):

1. **graph.json** – the graph for the AI to use
2. **graph.html** – an interactive map you can click and explore
3. **A report** – the most important nodes and the surprising connections

**Why it’s worth it:** When he asks a question, the AI reads only about **5 pages instead of 2,000**. It doesn’t read everything — it “walks” the graph starting from the nodes related to the question.

**It’s automatic:** A small script runs every time he types a prompt. It uses **no AI**. It finds the words from his question in the graph, walks 1–2 steps out to related nodes, and shows Claude the related notes **before Claude even answers**.

**Updating is fast:** Only new or changed notes get re-read. 82 new notes took about 13 minutes.

---

**PART 3 — ICM (Direction)**

ICM = **Interpretable Context Methodology** by Jake Van Clief. The idea is simple: **the folder structure itself IS the instructions.**

His workspace has:

* A **CLAUDE.md** file at the top — this is the **routing table** (a “directory” telling the AI where things are)
* Folders for **clients**, **projects**, and **references**
* A **schema** — the rules for how everything should be written

Every client and every project has one **short card** containing only:

* Status
* Next step
* Last update
* A **table of links**: where the code repo is, where the memory is, where the Obsidian note is

The card does **not** hold the full story. It only **points to where the story lives**.

**Example — he asks Claude: “What’s the status of this project?”**

1. Claude reads the routing table (CLAUDE.md)
2. Opens the project’s card
3. Follows the link to the right Obsidian folder
4. The graph shows it the related notes
   → Claude reads only a **handful of files**, not 1,000.

---

**THE MOST IMPORTANT RULE: “One home per fact”**
Every fact lives in **exactly one place**:

* **Status** → on the card
* **Full story** → in Obsidian
* **Connections** → in the graph
  If a fact lives in two places, one copy **will** eventually go out of date and the AI will give wrong answers.

---

**SUMMARY**

* **Obsidian** stores everything (memory)
* **Graphify** maps how everything connects, including links you missed (connections)
* **ICM** tells the AI which door to open first (direction)
  Result: the AI “knows” 1 million+ words but only reads the few pages it needs — so answers are faster, cheaper, and more accurate.

---

**HOW TO USE THIS METHOD (simple steps)**

1. **Store knowledge as plain Markdown files** in folders (Inbox, Projects, Areas, Resources, Archive).
2. **One idea per note.** Add front matter (type, tags, date, summary) and [[links]] to related notes.
3. **Let the AI write session notes** — at the end of work, say “save progress” so it records what was done, what failed, and what was decided.
4. **Run Graphify** on the folder to build the knowledge graph, and set it to update automatically when notes change.
5. **Add a hook/script** that searches the graph on every question and feeds the AI only the related notes.
6. **Create a CLAUDE.md routing table** plus a **short card** for each client/project (status, next step, last update, links).
7. **Follow “one home per fact”** — never copy the same fact into two places; link to it instead.
8. **Just ask.** The AI routes → reads the card → follows the link → gets related notes from the graph → answers.
