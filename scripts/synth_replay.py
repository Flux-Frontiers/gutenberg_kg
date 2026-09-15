#!/usr/bin/env python3
"""Replay a SynthesisTrace through Apple's on-device model via /usr/bin/fm.

The app writes one JSON per answer to Application Support/Diagnostics. Each
carries the exact instructions and prompt the model saw, so the on-device
path can be reproduced on any Apple-silicon Mac running macOS 27 without a
device, a signed build, or the app. `fm respond --greedy` on this Mac has
matched an iPhone trace byte for byte.

Only the on-device model: `fm` has no Private Cloud Compute route.

Usage:
    scripts/synth_replay.py TRACE.json [--instructions FILE] [--greedy]
                            [--question TEXT] [--show-prompt]

:param TRACE: a synthesis-*.json trace, pulled from a device with
    `xcrun devicectl device copy from ... --domain-type appDataContainer`.
:param --instructions: a file whose text replaces the trace's instructions,
    for prompt experiments against identical passages.
:param --greedy: `fm --greedy`, which is what temperature 0 amounts to.
:param --question: replace the question while keeping the passages.
"""

import argparse
import json
import pathlib
import re
import subprocess
import sys
import time

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("trace", type=pathlib.Path)
    ap.add_argument("--instructions", type=pathlib.Path)
    ap.add_argument("--greedy", action="store_true")
    ap.add_argument("--question")
    ap.add_argument("--show-prompt", action="store_true")
    args = ap.parse_args()

    trace = json.loads(args.trace.read_text())
    instructions = (
        args.instructions.read_text().strip() if args.instructions else trace["instructions"]
    )
    prompt = trace["prompt"]
    if args.question:
        prompt = re.sub(r"\nQuestion: .*\Z", f"\nQuestion: {args.question}", prompt, flags=re.S)
    if args.show_prompt:
        print(prompt, file=sys.stderr)

    cmd = ["/usr/bin/fm", "respond", "--no-stream", "-i", instructions]
    if args.greedy:
        cmd.append("--greedy")
    started = time.monotonic()
    out = subprocess.run(cmd, input=prompt, capture_output=True, text=True)
    elapsed = int((time.monotonic() - started) * 1000)
    answer = ANSI.sub("", out.stdout).strip()
    lines = [ln for ln in answer.splitlines() if ln.strip()]

    print(answer)
    print(
        f"\n[{elapsed} ms | {len(answer)} chars | {len(lines)} lines, "
        f"{len(set(lines))} unique | trace: {trace['modelDescription']} "
        f"T={trace['temperature']} {trace['answerCharacters']} chars]",
        file=sys.stderr,
    )
    if out.returncode:
        print(ANSI.sub("", out.stderr), file=sys.stderr)
    return out.returncode


if __name__ == "__main__":
    sys.exit(main())
