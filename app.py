import argparse
import sys
import os

from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from agent.core import AgentCore
from memory.manager import MemoryManager


def main():
    parser = argparse.ArgumentParser(
        description="AI Quiz Builder Agent — builds quiz apps from natural language briefs"
    )
    parser.add_argument("brief", nargs="?", help="Quiz app brief (e.g., 'Build a trivia quiz about space')")
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive REPL mode",
    )
    args = parser.parse_args()

    # Initialize systems
    memory = MemoryManager()
    agent = AgentCore(memory=memory)

    print("=" * 60)
    print("  AI Quiz Builder Agent")
    print("  Builds complete quiz apps from your description")
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

            print()
            try:
                result = agent.run(user_input)
                print(f"\n{'=' * 60}")
                print(result)
                print(f"{'=' * 60}\n")
            except Exception as e:
                print(f"\nError: {e}\n")

            # Reset conversation for next quiz build (memory persists)
            agent.reset()
    else:
        # Single-shot mode
        print(f"\nBrief: {args.brief}\n")
        try:
            result = agent.run(args.brief)
            print(f"\n{'=' * 60}")
            print(result)
            print(f"{'=' * 60}")
        except Exception as e:
            print(f"\nError: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
