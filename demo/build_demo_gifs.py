"""Build the README demo GIFs from real command output.

vhs cannot record on native Windows (charmbracelet/vhs#631: ttyd never
starts), so this script does what vhs does one layer down: run each demo
command for real, capture its ANSI output, compose an asciicast v2 file
with simulated keystroke timing, and render it with agg.

Usage, from the repo root:

    python demo/build_demo_gifs.py

Needs on PATH: python, jq, agg. Network access for the pip install step.
Writes docs/assets/demo-core.gif and docs/assets/demo-agent-safety.gif.
Every byte of command output in the GIFs is a real capture; only the
keystroke timing is synthesized, same as a vhs recording.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "docs" / "assets"
VENV = Path(tempfile.gettempdir()) / "fam-demo-venv"
SCRIPTS = VENV / "Scripts"
COLS, ROWS = 118, 32
TYPE_S = 0.035


def capture(argv, cwd):
    env = dict(os.environ)
    env.update(
        FORCE_COLOR="1",
        COLUMNS=str(COLS),
        PIP_DISABLE_PIP_VERSION_CHECK="1",
        PYTHONIOENCODING="utf-8",
        PYTHONUTF8="1",
        TERM="xterm-256color",
    )
    proc = subprocess.run(argv, cwd=cwd, env=env, capture_output=True)
    out = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
    if proc.returncode != 0:
        sys.exit(f"FAILED ({proc.returncode}): {argv}\n{out}")
    return out.replace("\r\n", "\n").replace("\n", "\r\n")


def build_cast(steps, cwd, prompt):
    events, t = [], 0.5
    for display, argv, pause in steps:
        events.append([round(t, 3), "o", prompt])
        t += 0.6
        for i, ch in enumerate(display):
            events.append([round(t, 3), "o", ch])
            t += TYPE_S + (i % 3) * 0.008
        t += 0.35
        events.append([round(t, 3), "o", "\r\n"])
        t += 0.25
        out = capture(argv, cwd)
        lines = out.split("\r\n")
        for i, line in enumerate(lines):
            tail = "\r\n" if i < len(lines) - 1 else ""
            events.append([round(t, 3), "o", line + tail])
            t += 0.012 if i < 80 else 0.0
        t += pause
    events.append([round(t, 3), "o", prompt])
    header = {
        "version": 2,
        "width": COLS,
        "height": ROWS,
        "env": {"TERM": "xterm-256color", "SHELL": "powershell"},
    }
    return "\n".join(json.dumps(e) for e in [header] + events)


def render(cast_text, gif_path):
    with tempfile.NamedTemporaryFile(
        "w", suffix=".cast", delete=False, encoding="utf-8"
    ) as f:
        f.write(cast_text)
        cast_path = f.name
    subprocess.run(
        ["agg", "--theme", "dracula", "--font-size", "16",
         "--last-frame-duration", "4", cast_path, str(gif_path)],
        check=True,
    )
    os.unlink(cast_path)
    print(f"wrote {gif_path} ({gif_path.stat().st_size / 1e6:.2f} MB)")


def fresh_dir(name):
    d = Path(tempfile.gettempdir()) / name
    subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(d)], capture_output=True)
    d.mkdir(parents=True)
    return d


def main():
    # A subst drive keeps real user paths out of the recorded frames.
    drive = next(
        (f"{c}:" for c in "XYZW" if not Path(f"{c}:\\").exists()), None
    ) or sys.exit("no free drive letter for subst")
    run1 = fresh_dir("fam-demo-run")
    prompt = f"\x1b[1mPS {drive}\\>\x1b[0m "
    subprocess.run(["subst", drive, str(run1)], check=True)
    try:
        print("creating fresh venv (the pip install in clip 1 must be real)...")
        subprocess.run(
            [sys.executable, "-m", "venv", "--clear", str(VENV)], check=True
        )
        pip = str(SCRIPTS / "pip.exe")
        fam = str(SCRIPTS / "fabric-ai-meta.exe")
        cwd = drive + "\\"

        core = [
            ("pip install fabric-ai-meta",
             [pip, "install", "fabric-ai-meta"], 1.2),
            ("fabric-ai-meta analyze 'Adventure Works' --mock",
             [fam, "analyze", "Adventure Works", "--mock"], 3.0),
            ("jq -C '.measures[1]' output/adventure-works/ai-ready-schema.json",
             ["jq", "-C", ".measures[1]",
              "output/adventure-works/ai-ready-schema.json"], 6.0),
        ]
        render(build_cast(core, cwd, prompt), ASSETS / "demo-core.gif")

        subprocess.run(["subst", drive, "/d"], check=True)
        run2 = fresh_dir("fam-demo-run2")
        subprocess.run(["subst", drive, str(run2)], check=True)

        manifest = "enterprise-sales/capability-manifest.json"
        readiness = "enterprise-sales/agent-readiness.json"
        agent = [
            ("fabric-ai-meta export capability-manifest 'Enterprise Sales' "
             "--mock --output .",
             [fam, "export", "capability-manifest", "Enterprise Sales",
              "--mock", "--output", "."], 2.0),
            ("jq -C --arg m '[Ending Inventory]' "
             f"'.measures[]|select(.name==$m)' {manifest}",
             ["jq", "-C", "--arg", "m", "[Ending Inventory]",
              ".measures[]|select(.name==$m)", manifest], 6.0),
            ("fabric-ai-meta export agent-readiness 'Enterprise Sales' "
             "--mock --output .",
             [fam, "export", "agent-readiness", "Enterprise Sales", "--mock",
              "--output", "."], 2.0),
            ("jq -C '{score, summary, first_fix: .findings[0]}' " + readiness,
             ["jq", "-C", "{score, summary, first_fix: .findings[0]}",
              readiness], 7.0),
        ]
        render(build_cast(agent, cwd, prompt), ASSETS / "demo-agent-safety.gif")
    finally:
        subprocess.run(["subst", drive, "/d"], capture_output=True)


if __name__ == "__main__":
    main()
