<div align="center">

# orkmem

Permanent memory for AI agents that never shows an outdated fact as current.
One Python file, no dependencies.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![dependencies: none](https://img.shields.io/badge/dependencies-none-2ea44f)
![tests: 12 invariants](https://img.shields.io/badge/tests-12%20invariants-0f766e)
![license: MIT](https://img.shields.io/badge/license-MIT-blue)

</div>

orkmem is a command-line memory for coding and chat agents. The agent runs `memo` through its shell as it works:
- it writes one-line entries;
- at the start of every session, and again after every compaction, it reads its rules and current facts;
- it asks for anything older when it needs it.

A rule stays in front of the agent, in full, however old it gets. A fact that has been replaced is never shown as the current one.

![how orkmem works](docs/how-it-works.png)

## 🚀 Install

```sh
git clone https://github.com/orkait/orkmem
sh orkmem/install.sh
```

The installer copies `memo` to `~/.orkmem/memo`, creates the memory in `~/.orkmem/memory`, and prints a `## Memory` block. Paste that block at the top of your agent's `AGENTS.md` or `CLAUDE.md`. Running it again updates the tool and never touches a memory.

## 🧭 Commands

| Command | What it does |
|---|---|
| `memo wake [page [head]]` | Shows, in pages of at most 10,000 bytes: every active rule in full, expired rules, open items, the latest fact per subject, and the 24 most recent entries |
| `memo note "..."` | Appends one line of at most 280 bytes, then shows the 3 closest earlier entries |
| `memo ask <words>` | Searches the whole memory, 20 results per page. Current entries come first, newest first; a replaced entry is listed under its replacement |
| `memo open <id>` | Shows one entry whole, with what it replaced and what replaced it; `--around N` adds its neighbours |
| `memo drop <id> "why"` | Retires an entry that is wrong or outdated; the entry stays in the log |
| `memo guard [action]` | Says whether an active rule forbids an action; with no action given, it reads hook JSON on stdin |
| `memo import <optmem-dir>` | Adds the memories of an [OptMem](https://github.com/VictorTaelin/OptMem) `LOG.txt` that are not imported yet, so it can run again while old sessions still write to OptMem; `memo open '#12'` still finds OptMem memory #12 |
| `memo config [NAME=VALUE]` | Shows or changes `ENTRY_BYTES`, `PAGE_BYTES`, `RECENT_LINES`, `ASK_LINES` and `HINTS` |

## 📝 Two kinds of entry

| Kind | Written with | True until | Shown by wake |
|---|---|---|---|
| Rule | `memo note --rule [--user] "..."` | It is replaced (`--replaces <id>`) or dropped. `--until YYYY-MM-DD` makes it temporary | Always, in full, however old |
| Fact | `memo note [--subject <topic>] "..."` | A newer fact on the same subject replaces it automatically | The latest per subject, with its age |

| Flag | Meaning |
|---|---|
| `--user` | The user said it. Without it, the entry is marked as written by the agent |
| `--open` | A fact that stays under OPEN in wake until it is replaced or dropped |
| `--guard <regex>` | A rule a hook can enforce: `memo guard` denies any action that matches |
| `--replaces <id>` | This entry corrects an earlier one. An id can be shortened to its first 4 or more characters |

## 🛡️ Enforcing rules with a hook

`memo guard` can run as a Claude Code `PreToolUse` hook. It prints a deny decision as JSON, so a tool call that matches a `--guard` rule is blocked:

```json
{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "\"$HOME/.orkmem/memo\" guard"}]}]}}
```

```sh
memo note --rule --user --guard '^gh pr merge' "Merge only after the user's OK"
```

For a Bash call the pattern is matched against the command; for other tools, against the tool input as JSON. If the input cannot be read or the memory is damaged, the hook denies rather than letting the call through.

## 📁 Files

```
~/.orkmem/
  memo            the tool: one Python 3 file, no dependencies
  memory/
    LOG.jsonl     every entry, one JSON object per line, append-only
    HEAD          the id of the last entry
    config        the sizes, written by memo config
```

How the files are kept safe:
- An entry's id is a hash of its contents and of the previous id.
- Every read checks the whole chain, and checks that `HEAD` is in it.
- An edited, reordered or truncated log is refused with "The memory is damaged" rather than served.
- A half-written last line, left by a crash, is dropped on the next write.
- Writers take a lock, so parallel sessions append in order.

Set `$MEMORY_DIR` to keep the memory elsewhere. Only `memo init` creates a memory, so a typo in `$MEMORY_DIR` fails loudly instead of starting an empty one.

## 🔁 How it differs from OptMem

| | OptMem | orkmem |
|---|---|---|
| Identity | Position in a fixed-width file | A hash of the entry, chained to the one before |
| Older memories | A binary tree of one-line summaries the agent writes | No summaries: entries stay whole, and `ask` finds them |
| Start of a session | 96 lines; older memories are shown ever coarser | All active rules in full, the latest fact per subject, and recent entries |
| Search | Regex, oldest first, capped at 20 KB | Words; current and newest first; 20 per page |
| Corrections | Not linked | `--replaces`, same-subject facts, and `drop` |
| Work on the agent's turn | Merging summaries after notes (`nap`) | None |

## ⚠️ Limits

| Limit | Detail |
|---|---|
| Reads are linear | Every command parses and checks the whole log. Measured: about 0.05 s at 2,500 entries and 0.85 s at 100,000. OptMem stays fast at a million entries |
| Platforms | Linux and macOS (`fcntl` locking). Windows is not supported yet |
| A stale copy of the whole folder | If a sync tool restores both `LOG.jsonl` and `HEAD` from an old copy, the memory is consistent and the loss cannot be seen |
| Imported memories | They arrive as facts, with no subjects or links. Restate standing rules with `memo note --rule --user` |
| Search is by words | "festival" does not find "Diwali" |

## 🧪 Tests

```sh
python3 test.py
```

The suite runs the real command line against temporary memories and checks 12 invariants:

| Area | What is checked |
|---|---|
| Rules | They stay whole after 3,000 imported entries; replaced and dropped rules leave the list; expired rules are surfaced |
| Facts | Only the newest fact per subject is current |
| Damage | Edited, truncated and reordered logs are refused; a torn write is repaired |
| Concurrency | 8 parallel writers neither fork nor lose an entry |
| Paging | Every page fits, and pages do not shift |
| `ask` | Results are bounded |
| `guard` | It denies only what active rules forbid, and fails closed |
| Input | Bad input is refused |
| Import | OptMem ids survive import; running it again adds only what is new |

## 🧾 The prompt

`memo init` prints this block. It is the whole integration.

```markdown
## Memory

Your memory is orkmem. The tool is `~/.orkmem/memo`; the memory is in `~/.orkmem/memory`.

### At startup and after every compaction (mandatory)

Your first action, and your first action after a compaction: `~/.orkmem/memo wake`.
Read page after page until one ends with "End of memory." Every RULE applies,
however old. A NOW fact is the last thing seen: check it again before you act on it.

### While working: write it down (mandatory)

- `~/.orkmem/memo note --rule --user "..."` when the user says how things must be done.
- `~/.orkmem/memo note --subject <topic> "..."` for a fact that can change (a version, a
  status, a place); a newer note on the same subject replaces the older one.
- `~/.orkmem/memo note "..."` for anything else worth keeping: a decision and its reason,
  a result, a lesson. One line, at most 280 bytes. Do not repeat what is there.
- `--replaces <id>` when a note corrects an earlier one; `~/.orkmem/memo drop <id> "why"`
  when one is wrong. When `note` lists a closest earlier entry your note makes
  outdated, drop it.

### When you need something old

`~/.orkmem/memo ask <words>` lists current entries first and marks outdated ones.
`~/.orkmem/memo open <id>` shows one entry whole, with what it replaced and what replaced it.

The files in `~/.orkmem/memory` change only through the tool; it refuses a damaged memory.

### Helpers you start

Memory belongs to the main session. Tell any helper agent you start: `Do not run memo.`
```

## 📄 License

MIT. See [LICENSE](LICENSE).

## 🙏 Credits

orkmem grew out of [OptMem](https://github.com/VictorTaelin/OptMem) by [Victor Taelin](https://github.com/VictorTaelin). OptMem's idea is a permanent, append-only memory that an agent uses through one small script and a short prompt.

orkmem keeps that shape. It changes how memories are identified, shown and corrected, and it was written from scratch: it contains no OptMem code. `memo import` reads OptMem's `LOG.txt`, so an existing OptMem memory can move over.
