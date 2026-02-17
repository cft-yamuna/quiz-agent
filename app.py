import argparse
import subprocess
import sys
import os
import webbrowser

from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from agent.core import AgentCore, AgentStopped
from memory.manager import MemoryManager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _add_figma_hint(user_input: str) -> str:
    """Append Figma hint if Figma is configured and not already mentioned."""
    figma_url = os.environ.get("FIGMA_URL", "")
    if figma_url or os.environ.get("FIGMA_FILE_KEY"):
        if "figma" not in user_input.lower() and "design" not in user_input.lower():
            hint = (
                "\n\n[System: A Figma design file is connected. "
                "Use fetch_figma_design to get the design specs and match them exactly."
            )
            # If URL has node-id, tell the agent it's page-specific
            if "node-id=" in figma_url:
                hint += (
                    " The Figma URL points to a SPECIFIC page/section — "
                    "focus only on the frames returned, do not look for other pages."
                )
            hint += "]"
            user_input += hint
    return user_input


def _find_latest_project():
    """Find the most recently modified project in output/."""
    output_dir = os.path.join(BASE_DIR, "output")
    if not os.path.exists(output_dir):
        return None
    projects = []
    for item in os.listdir(output_dir):
        project_path = os.path.join(output_dir, item)
        if os.path.isdir(project_path):
            mtime = os.path.getmtime(project_path)
            projects.append((item, project_path, mtime))
    if not projects:
        return None
    projects.sort(key=lambda x: x[2], reverse=True)
    return projects[0]  # (name, path, mtime)


def _offer_run_project():
    """After a build, offer to run the project dev server."""
    project = _find_latest_project()
    if not project:
        return

    name, project_dir, _ = project
    has_pkg = os.path.exists(os.path.join(project_dir, "package.json"))

    if not has_pkg:
        # Static project — offer to open in browser
        index_html = os.path.join(project_dir, "index.html")
        if os.path.exists(index_html):
            try:
                answer = input(f"\n  Run '{name}'? Open in browser (y/n): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return
            if answer in ("y", "yes"):
                webbrowser.open(f"file:///{os.path.abspath(index_html)}")
                print(f"  Opened {index_html} in browser.\n")
        return

    # React/Node project — offer to start dev server
    try:
        answer = input(f"\n  Run '{name}'? Start dev server (y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return

    if answer not in ("y", "yes"):
        return

    # Install dependencies if needed
    if not os.path.isdir(os.path.join(project_dir, "node_modules")):
        print("  Installing dependencies...")
        install = subprocess.run(
            "npm install",
            shell=True,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if install.returncode != 0:
            print(f"  npm install failed: {install.stderr[:300]}")
            return

    # Start dev server
    print("  Starting dev server on http://localhost:5173 ...")
    proc = subprocess.Popen(
        "npm run dev -- --port 5173 --host",
        shell=True,
        cwd=project_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait briefly then open browser
    import time
    time.sleep(2)
    webbrowser.open("http://localhost:5173")
    print("  Dev server running. Press Ctrl+C to stop.\n")

    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("\n  Dev server stopped.\n")


def run_cli():
    """Run the agent in CLI mode (interactive or single-shot)."""
    parser = argparse.ArgumentParser(
        description="AI Quiz Builder Agent — builds quiz apps from natural language briefs"
    )
    parser.add_argument("brief", nargs="?", help="Quiz app brief (e.g., 'Build a trivia quiz about space')")
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive REPL mode",
    )
    parser.add_argument(
        "--figma",
        action="store_true",
        help="Auto-fetch design from Figma and use it as the visual reference",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Launch the web interface",
    )
    args = parser.parse_args()

    # Web interface mode
    if args.web:
        from web.server import start_server
        start_server()
        return

    # Initialize systems
    memory = MemoryManager()
    agent = AgentCore(memory=memory)

    print("=" * 60)
    print("  AI Quiz Builder Agent")
    print("  Builds complete React quiz apps from your description")
    if args.figma or os.environ.get("FIGMA_URL") or os.environ.get("FIGMA_FILE_KEY"):
        print("  Figma design connected")
    print("  Press Ctrl+C during a build to stop it")
    print("=" * 60)

    if args.interactive or not args.brief:
        # Interactive REPL mode
        print("\nType your quiz brief, or 'quit' to exit.")
        print("Each message starts a fresh quiz build.\n")

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                print("Goodbye!")
                break
            if user_input.lower() == "stop":
                agent.stop()
                print("Stop requested.\n")
                continue

            user_input = _add_figma_hint(user_input)

            print()
            try:
                result = agent.run(user_input)
                print(f"\n{'=' * 60}")
                print(result)
                print(f"{'=' * 60}\n")
                _offer_run_project()
            except KeyboardInterrupt:
                agent.stop()
                print(f"\n{'=' * 60}")
                print("  Build stopped. Files created so far are saved.")
                print(f"  Iteration reached: {agent.iteration_count}")
                print(f"{'=' * 60}\n")
            except AgentStopped:
                print(f"\n{'=' * 60}")
                print("  Build stopped. Files created so far are saved.")
                print(f"  Iteration reached: {agent.iteration_count}")
                print(f"{'=' * 60}\n")
            except Exception as e:
                print(f"\nError: {e}\n")

            # Reset conversation for next quiz build (memory persists)
            agent.reset()
    else:
        # Single-shot mode
        brief = _add_figma_hint(args.brief)

        print(f"\nBrief: {args.brief}\n")
        try:
            result = agent.run(brief)
            print(f"\n{'=' * 60}")
            print(result)
            print(f"{'=' * 60}")
            _offer_run_project()
        except KeyboardInterrupt:
            print(f"\n{'=' * 60}")
            print("  Build stopped by user.")
            print(f"{'=' * 60}")
        except AgentStopped:
            print(f"\n{'=' * 60}")
            print("  Build stopped by user.")
            print(f"{'=' * 60}")
        except Exception as e:
            print(f"\nError: {e}")
            sys.exit(1)


if __name__ == "__main__":
    run_cli()
