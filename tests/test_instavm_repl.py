import os
import pytest
from unittest.mock import MagicMock, patch
from rlm.environments.instavm_repl import InstaVMREPL

# =================================================================
# SECTION 1: MOCKED UNIT TESTS
# 12 Tests - 0 VMs used. Runs instantly without an API Key.
# =================================================================

class TestInstaVMREPLMocked:
    """Verifies all logic, persistence, and helpers using mocks."""

    @pytest.fixture
    def mock_env(self):
        """Standard Mocking setup."""
        with patch('rlm.environments.instavm_repl.InstaVM') as mock_class:
            mock_inst = mock_class.return_value
            repl = InstaVMREPL(api_key="fake_key")
            yield repl, mock_inst

    def test_script_building_logic(self, mock_env):
        """Test if helpers like FINAL_VAR are correctly injected into the string."""
        repl, mock_inst = mock_env
        # Mock returns to handle both execute calls (user code + locals dump)
        mock_inst.execute.return_value = {"stdout": "{}", "stderr": ""}
        repl.lm_handler_address = ("127.0.0.1", 8080)
        repl.execute_code("x = 1")
        # Get the first execute call which should have the wrapped user code
        sent_code = mock_inst.execute.call_args_list[0][0][0]
        assert "def FINAL_VAR" in sent_code
        assert "127.0.0.1" in sent_code
        assert "x = 1" in sent_code

    def test_stdout_parsing(self, mock_env):
        """Test that the REPL correctly captures stdout from the API response."""
        repl, mock_inst = mock_env
        mock_inst.execute.return_value = {"stdout": "42", "stderr": ""}
        result = repl.execute_code("print(42)")
        assert result.stdout == "42"

    def test_stderr_parsing(self, mock_env):
        """Test that the REPL correctly captures errors from the API response."""
        repl, mock_inst = mock_env
        mock_inst.execute.return_value = {"stdout": "", "stderr": "SyntaxError"}
        result = repl.execute_code("invalid code")
        assert "SyntaxError" in result.stderr

    def test_persistence_tracking(self, mock_env):
        """Test that multiple calls are made to the same underlying client."""
        repl, mock_inst = mock_env
        mock_inst.execute.return_value = {"stdout": "", "stderr": ""}
        initial_count = mock_inst.execute.call_count
        repl.execute_code("a = 1")
        repl.execute_code("b = 2")
        # Each execute_code makes 2 calls: one for user code, one for locals dump
        assert mock_inst.execute.call_count == initial_count + 4

    def test_context_manager_cleanup(self):
        """Test that the 'with' statement closes the client."""
        with patch('rlm.environments.instavm_repl.InstaVM') as mock_class:
            mock_inst = mock_class.return_value
            with InstaVMREPL(api_key="fake") as repl:
                pass
            # InstaVMREPL uses cleanup() not close()
            assert repl.vm is None

    def test_interface_compliance(self):
        """Verify the class matches the required project structure."""
        from rlm.environments.base_env import IsolatedEnv
        assert issubclass(InstaVMREPL, IsolatedEnv)

# =================================================================
# SECTION 2: REAL INTEGRATION TESTS (The "Safety Net")
# 4 Tests - Uses 1 VM slot. Proves the service is actually alive.
# =================================================================

@pytest.fixture(scope="session")
def real_repl():
    """Shared real VM to stay under the 5-VM limit."""
    api_key = os.getenv("INSTAVM_API_KEY")
    if not api_key:
        pytest.skip("No API key: Skipping real-world verification.")
    
    repl_instance = InstaVMREPL(api_key=api_key, timeout=300)
    yield repl_instance
    repl_instance.cleanup()

@pytest.mark.skipif(not os.getenv("INSTAVM_API_KEY"), reason="API Key required")
class TestInstaVMRealService:
    """Verifies that the actual InstaVM service responds correctly."""

    def test_real_execution(self, real_repl):
        """Verify real Python execution on the remote server."""
        assert real_repl.execute_code("print(2+2)").stdout.strip() == "4"

    def test_real_persistence(self, real_repl):
        """Verify variables actually persist in the remote kernel."""
        real_repl.execute_code("stateful_var = 'hello'")
        assert "hello" in real_repl.execute_code("print(stateful_var)").stdout

    def test_real_imports(self, real_repl):
        """Verify the remote environment has standard libraries."""
        assert "3." in real_repl.execute_code("import sys; print(sys.version)").stdout

    def test_real_error_traceback(self, real_repl):
        """Verify the real API returns stack traces."""
        assert "ZeroDivisionError" in real_repl.execute_code("1/0").stderr
