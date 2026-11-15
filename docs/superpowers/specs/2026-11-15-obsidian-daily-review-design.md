# obsidian-daily-review skill design spec

- Date: 2026-11-15
- Status: approved

## Goal

Ideas are captured into Obsidian daily notes from an iOS shortcut as one bullet per idea, with no
tags at capture time. An AI review later adds tags, so related ideas can be gathered by tag (for
example from a Knowledge Base page about one technology).

## Behavior

- Trigger: the user asks to review or tag today's daily note, or the notes for a date or range.
  No date means today.
- For each bullet without a tag, append 1 to 3 topic tags at the end of the line.
- Never change the bullet text, order or frontmatter; never create, move or delete notes.
- Bullets that already have a tag are skipped, so a second run changes nothing.
- Tags: reuse the vault's existing tags first; new tags are lowercase English kebab-case. When
  nothing fits with confidence, leave the bullet untagged and report it.
- Report: notes reviewed, tags added per bullet, new tags, bullets left untagged.

## Constraints

- Public repo: no personal paths. The vault path comes from `OBSIDIAN_VAULT`; when it is missing
  the skill asks for it.
- Daily notes folder and file name format come from the vault's `.obsidian/daily-notes.json`.
- Bullets may begin with any time stamp format, such as `［下午9:05］` from the shortcut.
- `metadata.web: "false"`: web apps cannot reach the vault.

## Approaches

| Approach | Trade-off | Decision |
|---|---|---|
| Instructions only (SKILL.md) | Simple; relies on the agent editing lines carefully | Chosen |
| Script that rewrites the note | Exact edits, but tag choice still needs the model, so the script only moves text | Not now |

## Later

- When the vault's Knowledge Base categories are designed, the skill will read that category list
  as the preferred tag vocabulary.
