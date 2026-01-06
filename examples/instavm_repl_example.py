"""
InstaVM REPL example with code execution.

Setup:
    1. Install instavm: uv add instavm
    2. Set API key: export INSTAVM_API_KEY=...
    3. Run: python -m examples.instavm_repl_example

InstaVM provides fast Firecracker microVMs with stateful execution.
"""

import os
from rlm.environments.instavm_repl import InstaVMREPL


def main():
    api_key = os.getenv("INSTAVM_API_KEY")
    if not api_key:
        print("Error: INSTAVM_API_KEY environment variable not set")
        print("Set it with: export INSTAVM_API_KEY=...")
        return

    print("=" * 50)
    print("InstaVM REPL Example")
    print("=" * 50)

    # Basic execution
    print("\n[1] Basic code execution")
    with InstaVMREPL(api_key=api_key, timeout=30) as repl:
        result = repl.execute_code("x = 1 + 2")
        print(f"  x = 1 + 2 → locals: {result.locals}")

        result = repl.execute_code("print(x * 2)")
        print(f"  print(x * 2) → {result.stdout.strip()}")

        # Test state persistence
        result = repl.execute_code("y = x * 10")
        result = repl.execute_code("print(y)")
        print(f"  State persists → y = {result.stdout.strip()}")

        # Test complex operations
        result = repl.execute_code("total = sum([i**2 for i in range(10)])")
        result = repl.execute_code("print(total)")
        print(f"  Sum of squares → {result.stdout.strip()}")

    # Test with context loading
    print("\n[2] Context loading")
    with InstaVMREPL(api_key=api_key, timeout=30) as repl:
        repl.load_context({"name": "InstaVM", "speed": "fast"})
        result = repl.execute_code("print(f'Context: {context}')")
        print(f"  Loaded context → {result.stdout.strip()}")

    print("\n" + "=" * 50)
    print("Done!")
    print("=" * 50)


if __name__ == "__main__":
    main()
