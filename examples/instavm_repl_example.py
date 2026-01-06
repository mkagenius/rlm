"""
InstaVM REPL example with code execution and LLM queries.

Setup:
    1. Install instavm: uv add instavm
    2. Set API key: export INSTAVM_API_KEY=...
    3. Run: python -m examples.instavm_repl_example

InstaVM provides fast Firecracker microVMs with stateful execution.
"""

import os
from rlm.clients.base_lm import BaseLM
from rlm.core.lm_handler import LMHandler
from rlm.core.types import ModelUsageSummary, UsageSummary
from rlm.environments.instavm_repl import InstaVMREPL


class MockLM(BaseLM):
    def __init__(self):
        super().__init__(model_name="mock")

    def completion(self, prompt):
        return f"Mock: {str(prompt)[:50]}"

    async def acompletion(self, prompt):
        return self.completion(prompt)

    def get_usage_summary(self):
        return UsageSummary({"mock": ModelUsageSummary(1, 10, 10)})

    def get_last_usage(self):
        return self.get_usage_summary()


def main():
    if not os.getenv("INSTAVM_API_KEY"):
        print("Error: INSTAVM_API_KEY environment variable not set")
        print("Set it with: export INSTAVM_API_KEY=...")
        return

    print("=" * 50)
    print("InstaVM REPL Example")
    print("=" * 50)

    # Basic execution (no LLM)
    print("\n[1] Basic code execution")
    with InstaVMREPL(timeout=30) as repl:
        result = repl.execute_code("x = 1 + 2")
        print(f"  x = 1 + 2 → locals: {result.locals}")

        result = repl.execute_code("print(x * 2)")
        print(f"  print(x * 2) → {result.stdout.strip()}")

        # Test state persistence
        result = repl.execute_code("y = x * 10")
        result = repl.execute_code("print(y)")
        print(f"  State persists → y = {result.stdout.strip()}")

    # With LLM handler
    print("\n[2] With LLM handler")
    with LMHandler(client=MockLM()) as handler:
        print(f"  Handler at {handler.address}")

        with InstaVMREPL(
            timeout=30,
            lm_handler_address=handler.address
        ) as repl:
            result = repl.execute_code('r = llm_query("Hello!")')
            print(f"  llm_query → stderr: {result.stderr or '(none)'}")

            result = repl.execute_code("print(r)")
            print(f"  Response: {result.stdout.strip()}")

            result = repl.execute_code('rs = llm_query_batched(["Q1", "Q2"])')
            result = repl.execute_code("print(len(rs))")
            print(f"  Batched count: {result.stdout.strip()}")

            result = repl.execute_code('print(FINAL_VAR("rs"))')
            print(f"  FINAL_VAR: {result.stdout.strip()}")

    print("\n" + "=" * 50)
    print("Done!")
    print("=" * 50)


if __name__ == "__main__":
    main()
