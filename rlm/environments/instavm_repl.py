"""
InstaVM REPL environment for RLM.

Executes Python code in InstaVM's Firecracker microVMs with sub-200ms startup.
Provides stateful execution between code blocks.
"""

import json
import time
from typing import Any

from rlm.core.comms_utils import LMRequest, send_lm_request, send_lm_request_batched
from rlm.core.types import REPLResult, RLMChatCompletion
from rlm.environments.base_env import IsolatedEnv

try:
    from instavm import InstaVM
except ImportError:
    raise ImportError(
        "InstaVM is not installed. Install it with: pip install instavm"
    )


class InstaVMREPL(IsolatedEnv):
    """
    InstaVM REPL environment that runs Python code in InstaVM microVMs.

    InstaVM provides:
    - Fast Firecracker microVMs (sub-200ms startup)
    - Stateful execution between code blocks
    - Full network access
    - Isolated execution environment

    The InstaVM client handles state persistence automatically,
    so variables persist across execute() calls.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.instavm.io",
        timeout: int = 300,
        lm_handler_address: tuple[str, int] | None = None,
        context_payload: dict | list | str | None = None,
        setup_code: str | None = None,
        **kwargs,
    ):
        """
        Initialize InstaVM environment.

        Args:
            api_key: InstaVM API key (if None, reads from INSTAVM_API_KEY env var)
            base_url: InstaVM API base URL (default: https://api.instavm.io)
            timeout: Default timeout for code execution in seconds (default: 300)
            lm_handler_address: (host, port) tuple for LLM handler (injected at runtime)
            context_payload: Initial context/data to load (injected at runtime)
            setup_code: Code to execute during setup (injected at runtime)
            **kwargs: Additional arguments (ignored)
        """
        super().__init__(**kwargs)

        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.lm_handler_address = lm_handler_address

        # Initialize InstaVM client
        self.vm: InstaVM | None = None

        # Track LLM calls made during execution
        self.pending_llm_calls: list[RLMChatCompletion] = []

        # Setup the environment
        self.setup()

        # Load initial context if provided
        if context_payload is not None:
            self.load_context(context_payload)

        # Execute setup code if provided
        if setup_code:
            self.execute_code(setup_code)

    def setup(self):
        """Initialize the InstaVM client."""
        # InstaVM client will handle connection on first execute()
        init_kwargs = {
            "timeout": self.timeout,
        }

        if self.api_key:
            init_kwargs["api_key"] = self.api_key

        if self.base_url:
            init_kwargs["base_url"] = self.base_url

        self.vm = InstaVM(**init_kwargs)

    def load_context(self, context_payload: dict | list | str):
        """
        Load context into the InstaVM environment.

        Creates a 'context' variable in the VM with the provided data.
        """
        if isinstance(context_payload, str):
            # Escape the string for safe embedding
            escaped = context_payload.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
            context_code = f'context = """{escaped}"""'
        else:
            # Convert dict/list to JSON and load it
            context_json = json.dumps(context_payload)
            escaped_json = context_json.replace("\\", "\\\\").replace("'", "\\'")
            context_code = f"import json; context = json.loads('{escaped_json}')"

        self.execute_code(context_code)

    def execute_code(self, code: str) -> REPLResult:
        """
        Execute code in the InstaVM environment.

        InstaVM maintains state automatically, so variables from previous
        executions are available.

        Args:
            code: Python code to execute

        Returns:
            REPLResult with stdout, stderr, locals, execution_time, and rlm_calls
        """
        if self.vm is None:
            raise RuntimeError("InstaVM client not initialized. Call setup() first.")

        start_time = time.perf_counter()

        # Clear pending LLM calls from previous execution
        self.pending_llm_calls.clear()

        # Inject helper functions for LLM queries if lm_handler_address is provided
        if self.lm_handler_address:
            code = self._inject_llm_helpers(code)

        try:
            # Execute code in InstaVM
            result = self.vm.execute(code, timeout=self.timeout)

            execution_time = time.perf_counter() - start_time

            # Parse the result - InstaVM returns a dictionary
            if isinstance(result, dict):
                stdout = result.get("stdout", "")
                stderr = result.get("stderr", "")
                # InstaVM provides execution time in the response
                vm_execution_time = result.get("execution_time", execution_time)
            elif hasattr(result, "stdout"):
                # Fallback for object-based responses
                stdout = result.stdout if hasattr(result, "stdout") else str(result)
                stderr = result.stderr if hasattr(result, "stderr") else ""
                vm_execution_time = execution_time
            else:
                # Fallback for string responses
                stdout = str(result)
                stderr = ""
                vm_execution_time = execution_time

            # Try to get locals/variables if available
            # InstaVM may not provide this directly, so we'll try to extract it
            locals_dict = {}
            try:
                # Execute a variable dump to get current state
                dump_result = self.vm.execute(
                    "import json; print(json.dumps({k: repr(v) for k, v in globals().items() if not k.startswith('_') and k not in ['json', 'In', 'Out', 'get_ipython']}))",
                    timeout=10,
                )
                if dump_result:
                    dump_data = dump_result.get("stdout", "") if isinstance(dump_result, dict) else str(dump_result)
                    # Extract JSON from output (it might be mixed with other text)
                    import re
                    json_match = re.search(r'\{[^{}]*\}', dump_data)
                    if json_match:
                        locals_dict = json.loads(json_match.group())
            except Exception:
                # If we can't get locals, just return empty dict
                pass

            return REPLResult(
                stdout=stdout,
                stderr=stderr,
                locals=locals_dict,
                execution_time=vm_execution_time,
                rlm_calls=self.pending_llm_calls.copy(),
            )

        except Exception as e:
            execution_time = time.perf_counter() - start_time
            return REPLResult(
                stdout="",
                stderr=f"InstaVM execution error: {str(e)}",
                locals={},
                execution_time=execution_time,
                rlm_calls=self.pending_llm_calls.copy(),
            )

    def _inject_llm_helpers(self, code: str) -> str:
        """
        Inject LLM helper functions into the code.

        This allows code running in InstaVM to make LLM queries via the LM handler.
        Uses httpx which is pre-installed in InstaVM.
        """
        # We need to wrap the code to track _locals properly
        wrapped_code = f'''
import json

_LM_HANDLER_HOST = "{self.lm_handler_address[0]}"
_LM_HANDLER_PORT = {self.lm_handler_address[1]}

# Initialize _locals dict if it doesn't exist
if '_locals' not in globals():
    globals()['_locals'] = {{}}
_locals = globals()['_locals']

def llm_query(prompt, model=None):
    """Query the LM from within the sandbox."""
    try:
        import httpx
        with httpx.Client(timeout=300) as client:
            response = client.post(
                f"http://{{_LM_HANDLER_HOST}}:{{_LM_HANDLER_PORT}}/single",
                json={{"prompt": prompt, "model": model}}
            )
            data = response.json()
            if data.get("success"):
                return data.get("response", "")
            else:
                return f"Error: {{data.get('error', 'Unknown error')}}"
    except Exception as e:
        return f"Error: LM query failed - {{e}}"

def llm_query_batched(prompts, model=None):
    """Query the LM with multiple prompts."""
    try:
        import httpx
        with httpx.Client(timeout=300) as client:
            response = client.post(
                f"http://{{_LM_HANDLER_HOST}}:{{_LM_HANDLER_PORT}}/batched",
                json={{"prompts": prompts, "model": model}}
            )
            data = response.json()
            if data.get("success"):
                return data.get("responses", [])
            else:
                return [f"Error: {{data.get('error', 'Unknown error')}}"] * len(prompts)
    except Exception as e:
        return [f"Error: LM query failed - {{e}}"] * len(prompts)

def FINAL_VAR(variable_name):
    """Get the final value of a variable."""
    variable_name = variable_name.strip().strip("\\"\\'")
    # Check globals directly since InstaVM maintains state
    import sys
    frame = sys._getframe(1)
    if variable_name in frame.f_globals:
        return str(frame.f_globals[variable_name])
    elif variable_name in frame.f_locals:
        return str(frame.f_locals[variable_name])
    else:
        return f"Error: Variable '{{variable_name}}' not found"

# Execute user code
{code}

# Update _locals with newly created variables
import inspect
frame = inspect.currentframe()
for k, v in frame.f_locals.items():
    if not k.startswith('_') and k not in ['json', 'httpx', 'llm_query', 'llm_query_batched', 'FINAL_VAR', 'inspect', 'code']:
        _locals[k] = v
'''
        return wrapped_code

    def cleanup(self):
        """
        Clean up resources.

        InstaVM doesn't require explicit cleanup, but we can
        reset the client reference if needed.
        """
        self.vm = None
        self.pending_llm_calls.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False

    def __del__(self):
        self.cleanup()
