#!/usr/bin/env python3
"""orkmem invariants, checked through the real command line."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.realpath(__file__))
MEMO = os.path.join(HERE, "memo")
PAGE_BYTES = 10000
ASK_LINES = 20
WRITERS, NOTES_EACH = 8, 15
BULK = 3000
OPTMEM_RECORD = 320


def optmem_log(folder: str, texts: list[str]) -> str:
    os.makedirs(folder)
    with open(os.path.join(folder, "LOG.txt"), "wb") as f:
        f.writelines(f"#{i} 2026-11-01 {t}".encode().ljust(OPTMEM_RECORD - 1) + b"\n" for i, t in enumerate(texts))
    return folder


class Store:
    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "memory")
        self.run("init")

    def run(self, *args: str, stdin: str = "", ok: bool = True) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, MEMORY_DIR=self.dir)
        out = subprocess.run([sys.executable, MEMO, *args], input=stdin, env=env, capture_output=True, text=True, check=False)
        if ok and out.returncode:
            raise AssertionError(f"memo {' '.join(args)} failed: {out.stderr}")
        return out

    def note(self, *args: str) -> str:
        return self.run("note", *args).stdout.split()[1]

    def wake(self) -> str:
        first = self.run("wake").stdout
        pages, head = [first], first.split("as of ")[1].split()[0]
        while "More: memo wake" in pages[-1]:
            pages.append(self.run("wake", str(len(pages) + 1), head).stdout)
        return "\n".join(pages)

    def log(self) -> list[str]:
        with open(os.path.join(self.dir, "LOG.jsonl"), encoding="utf-8") as f:
            return f.read().splitlines(keepends=True)

    def rewrite(self, lines: list[str]) -> None:
        with open(os.path.join(self.dir, "LOG.jsonl"), "w", encoding="utf-8") as f:
            f.writelines(lines)


class Invariants(unittest.TestCase):
    def setUp(self) -> None:
        self.s = Store()

    def tearDown(self) -> None:
        self.s.tmp.cleanup()

    def test_rules_stay_whole_however_much_follows(self) -> None:
        rule = "Never merge design changes without the user's OK"
        old = optmem_log(os.path.join(self.s.tmp.name, "optmem"), [f"fact number {i} about the deploy" for i in range(BULK)])
        self.s.note("--rule", "--user", rule)
        self.assertIn("not empty", self.s.run("import", old, ok=False).stderr)
        fresh = Store()
        fresh.run("import", old)
        fresh.note("--rule", "--user", rule)
        for i in range(30):
            fresh.note(f"later fact {i}")
        self.assertIn(rule, fresh.wake().split("RECENT")[0])
        fresh.tmp.cleanup()

    def test_newest_fact_per_subject_is_the_only_current_one(self) -> None:
        old = self.s.note("--subject", "app.live", "live version is 77685930d")
        new = self.s.note("--subject", "app.live", "live version is 9de29cb0b")
        facts = self.s.wake().split("NOW")[1].split("RECENT")[0]
        self.assertIn("9de29cb0b", facts)
        self.assertNotIn("77685930d", facts)
        ask = self.s.run("ask", "live version").stdout.splitlines()
        self.assertIn(new[:8], ask[1])
        self.assertTrue(any(old[:8] in line and "replaced" in line for line in ask[2:]))

    def test_replaced_and_dropped_rules_leave_the_rule_list(self) -> None:
        a = self.s.note("--rule", "worker agents are fine when asked")
        b = self.s.note("--rule", "--replaces", a[:8], "no subagents at all")
        c = self.s.note("--rule", "for now, no OpenCode")
        self.s.run("drop", c[:8], "the user lifted it")
        rules = self.s.wake().split("RULES")[1].split("RECENT")[0]
        self.assertIn(b[:8], rules)
        self.assertNotIn(a[:8], rules)
        self.assertNotIn(c[:8], rules)

    def test_expired_rule_is_surfaced_for_the_user(self) -> None:
        self.s.note("--rule", "--until", "2020-01-01", "for now, no paid tests")
        self.assertIn("no paid tests", self.s.wake().split("EXPIRED")[1])

    def test_damage_is_refused_not_served(self) -> None:
        for i in range(5):
            self.s.note(f"fact {i}")
        good = self.s.log()
        cases = {
            "edited": [*good[:2], good[2].replace("fact 2", "fact 7"), *good[3:]],
            "lost tail": good[:-1],
            "reordered": [good[0], good[2], good[1], *good[3:]],
        }
        for name, lines in cases.items():
            with self.subTest(name):
                self.s.rewrite(lines)
                for cmd in (["wake"], ["ask", "fact"], ["note", "x"]):
                    out = self.s.run(*cmd, ok=False)
                    self.assertNotEqual(out.returncode, 0)
                    self.assertIn("damaged", out.stderr)
        self.s.rewrite(good)
        self.s.run("wake")

    def test_a_torn_append_is_repaired(self) -> None:
        self.s.note("fact one")
        with open(os.path.join(self.s.dir, "LOG.jsonl"), "a", encoding="utf-8") as f:
            f.write('{"n": 1, "half')
        self.s.note("fact two")
        self.assertEqual(len(self.s.log()), 2)

    def test_parallel_writers_never_fork_or_lose(self) -> None:
        def write(w: int) -> None:
            for i in range(NOTES_EACH):
                self.s.note(f"writer {w} note {i}")

        with ThreadPoolExecutor(WRITERS) as pool:
            list(pool.map(write, range(WRITERS)))
        lines = [json.loads(line) for line in self.s.log()]
        self.assertEqual([e["n"] for e in lines], list(range(WRITERS * NOTES_EACH)))
        self.assertEqual([e["prev"] for e in lines[1:]], [e["id"] for e in lines[:-1]])
        self.s.run("wake")

    def test_every_page_fits_and_pages_do_not_shift(self) -> None:
        for i in range(60):
            self.s.note("--rule", f"rule {i}: {'keep it whole ' * 15}")
        first = self.s.run("wake").stdout
        head = first.split("as of ")[1].split()[0]
        self.s.note("--rule", "a rule written between two pages")
        pages = [first]
        while "More: memo wake" in pages[-1]:
            pages.append(self.s.run("wake", str(len(pages) + 1), head).stdout)
        self.assertGreater(len(pages), 1)
        self.assertTrue(all(len(p.encode()) <= PAGE_BYTES for p in pages))
        self.assertIn("End of memory.", pages[-1])
        joined = "\n".join(pages)
        self.assertNotIn("written between", joined)
        self.assertTrue(all(f"rule {i}:" in joined for i in range(60)))

    def test_ask_is_bounded_forgiving_and_honest(self) -> None:
        for i in range(ASK_LINES + 10):
            self.s.note(f"deploy note {i}")
        out = self.s.run("ask", "-i", "deploy|release").stdout
        shown = [line for line in out.splitlines() if line.startswith("  ") and not line.startswith("   ")]
        self.assertLessEqual(len(shown), ASK_LINES)
        self.assertIn(f"deploy note {ASK_LINES + 9}", shown[0])
        self.assertIn("--page 2", out)
        self.assertIn("No match", self.s.run("ask", "kubernetes").stdout)

    def test_guard_blocks_only_what_an_active_rule_forbids(self) -> None:
        rule = self.s.note("--rule", "--guard", r"^gh pr merge", "merge only after the user's OK")
        hook = json.dumps({"tool_input": {"command": "gh pr merge 1881 --admin"}})

        def decision(stdin: str) -> str | None:
            out: dict[str, dict[str, str]] = json.loads(self.s.run("guard", stdin=stdin).stdout)
            return out.get("hookSpecificOutput", {}).get("permissionDecision")

        cases = [("forbidden", hook, "deny"), ("allowed", json.dumps({"tool_input": {"command": "ls"}}), None), ("garbled", "not json", "deny")]
        for name, stdin, want in cases:
            with self.subTest(name):
                self.assertEqual(decision(stdin), want)
        self.assertNotEqual(self.s.run("guard", "gh pr merge 7", ok=False).returncode, 0)
        self.s.run("drop", rule[:8], "the user lifted it")
        self.assertIsNone(decision(hook))

    def test_bad_input_is_refused_and_only_init_creates(self) -> None:
        cases = [("too long", ["note", "x" * 400]), ("two lines", ["note", "a\nb"]), ("unknown id", ["note", "--replaces", "ffffffff", "y"])]
        for name, args in cases:
            with self.subTest(name):
                self.assertNotEqual(self.s.run(*args, ok=False).returncode, 0)
        self.assertEqual(self.s.log(), [])
        missing = os.path.join(self.s.tmp.name, "typo")
        env = dict(os.environ, MEMORY_DIR=missing)
        out = subprocess.run([sys.executable, MEMO, "wake"], env=env, capture_output=True, text=True, check=False)
        self.assertNotEqual(out.returncode, 0)
        self.assertFalse(os.path.exists(missing))

    def test_imported_memories_keep_their_old_ids(self) -> None:
        self.s.run("import", optmem_log(os.path.join(self.s.tmp.name, "optmem"), ["first thing", "second thing", "third thing"]))
        self.assertIn("second thing", self.s.run("open", "#1").stdout)


if __name__ == "__main__":
    unittest.main()
