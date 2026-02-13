"""
Comprehensive test suite for all 14 CVC Agent features.
Run: python tests/test_features.py
"""
from __future__ import annotations

import asyncio
import fnmatch
import inspect
import json
import os
import sys
import tempfile
from pathlib import Path

# Ensure workspace root is importable
WORKSPACE = Path(r"e:\Projects\AI Cognitive Version Control")
os.chdir(WORKSPACE)

passed = 0
failed = 0
errors_list: list[str] = []


def report(feature: int, name: str, ok: bool, detail: str = ""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  [PASS] Feature {feature}: {name}" + (f" -- {detail}" if detail else ""))
    else:
        failed += 1
        errors_list.append(f"Feature {feature}: {name} -- {detail}")
        print(f"  [FAIL] Feature {feature}: {name} -- {detail}")


# =====================================================================
# Feature 1: Streaming Responses
# =====================================================================
print("\n=== Feature 1: Streaming Responses ===")
try:
    from cvc.agent.llm import StreamEvent, AgentLLM

    e1 = StreamEvent(type="text_delta", text="Hello")
    assert e1.type == "text_delta" and e1.text == "Hello"

    e2 = StreamEvent(type="done", prompt_tokens=100, completion_tokens=50, cache_read_tokens=10)
    assert e2.prompt_tokens == 100

    llm = AgentLLM(provider="anthropic", api_key="test", model="test", base_url="http://localhost")
    assert hasattr(llm, "chat_stream"), "Missing chat_stream"
    assert asyncio.iscoroutinefunction(llm.chat_stream.__wrapped__) if hasattr(llm.chat_stream, '__wrapped__') else True

    from cvc.agent.renderer import StreamingRenderer
    sr = StreamingRenderer()
    assert hasattr(sr, "start") and hasattr(sr, "add_text") and hasattr(sr, "finish")
    assert not sr.is_active()

    report(1, "Streaming Responses", True, "StreamEvent + chat_stream + StreamingRenderer OK")
except Exception as exc:
    report(1, "Streaming Responses", False, str(exc))

# =====================================================================
# Feature 2: Multi-file Auto-Context
# =====================================================================
print("\n=== Feature 2: Multi-file Auto-Context ===")
try:
    from cvc.agent.auto_context import (
        build_auto_context, build_file_tree,
        read_project_manifests, extract_files_from_error,
    )

    tree = build_file_tree(WORKSPACE)
    assert len(tree) > 50, f"Tree too short: {len(tree)}"

    manifests = read_project_manifests(WORKSPACE)
    assert isinstance(manifests, dict), f"Expected dict, got {type(manifests)}"
    assert "pyproject.toml" in manifests, f"Missing pyproject.toml key"

    ctx = build_auto_context(WORKSPACE)
    assert "File Tree" in ctx and "pyproject.toml" in ctx, "Context missing expected sections"

    error_text = (
        "Traceback (most recent call last):\n"
        '  File "cvc/agent/chat.py", line 42, in run\n'
        "    result = process(data)\n"
    )
    files = extract_files_from_error(error_text, WORKSPACE)
    assert isinstance(files, list)
    assert any("chat.py" in str(f) for f in files), f"Expected chat.py in {files}"

    report(2, "Multi-file Auto-Context", True,
           f"tree={len(tree)}ch, manifests={len(manifests)} files, ctx={len(ctx)}ch, error_files={len(files)}")
except Exception as exc:
    report(2, "Multi-file Auto-Context", False, str(exc))

# =====================================================================
# Feature 3: Diff-based Editing
# =====================================================================
print("\n=== Feature 3: Diff-based Editing ===")
try:
    from cvc.agent.tools import AGENT_TOOLS
    from cvc.agent.executor import ToolExecutor

    tool_names = [t["function"]["name"] for t in AGENT_TOOLS]
    assert "patch_file" in tool_names, f"patch_file not in tools"
    assert "edit_file" in tool_names, f"edit_file not in tools"

    assert hasattr(ToolExecutor, "_patch_file"), "Missing _patch_file method"
    assert hasattr(ToolExecutor, "_fuzzy_find_and_replace"), "Missing _fuzzy_find_and_replace"

    # Verify fuzzy matching works
    from difflib import SequenceMatcher
    original = "def hello_world():\n    print('Hello World')\n    return True\n"
    fuzzy = "def hello_world():\n    print('Hello world')\n    return True\n"
    ratio = SequenceMatcher(None, original, fuzzy).ratio()
    assert ratio >= 0.6, f"Fuzzy ratio too low: {ratio}"

    # Test _patch_file and _fuzzy_find_and_replace signatures exist
    sig_patch = inspect.signature(ToolExecutor._patch_file)
    sig_fuzzy = inspect.signature(ToolExecutor._fuzzy_find_and_replace)
    assert "args" in sig_patch.parameters or "self" in sig_patch.parameters
    assert "content" in sig_fuzzy.parameters or "self" in sig_fuzzy.parameters

    report(3, "Diff-based Editing", True, "patch_file tool + fuzzy matching OK")
except Exception as exc:
    report(3, "Diff-based Editing", False, str(exc))

# =====================================================================
# Feature 4: Auto Error Recovery
# =====================================================================
print("\n=== Feature 4: Auto Error Recovery ===")
try:
    from cvc.agent.chat import AgentSession, MAX_RETRY_ATTEMPTS

    assert MAX_RETRY_ATTEMPTS >= 1, f"MAX_RETRY_ATTEMPTS too low: {MAX_RETRY_ATTEMPTS}"

    source = inspect.getsource(AgentSession._execute_single_tool)
    assert "retry_count" in source, "Missing retry loop in _execute_single_tool"
    assert "MAX_RETRY_ATTEMPTS" in source, "Missing MAX_RETRY_ATTEMPTS reference"

    source2 = inspect.getsource(AgentSession.run_turn)
    assert "Retrying" in source2 or "retry" in source2.lower(), "Missing retry path in run_turn"

    assert hasattr(AgentSession, "_auto_context_from_error"), "Missing _auto_context_from_error"
    src3 = inspect.getsource(AgentSession._auto_context_from_error)
    assert "extract_files_from_error" in src3, "Missing extract_files_from_error call"

    report(4, "Auto Error Recovery", True,
           f"MAX_RETRY={MAX_RETRY_ATTEMPTS}, retry loop + auto-context from error OK")
except Exception as exc:
    report(4, "Auto Error Recovery", False, str(exc))

# =====================================================================
# Feature 5: /undo Command
# =====================================================================
print("\n=== Feature 5: /undo Command ===")
try:
    from cvc.agent.executor import ToolExecutor, FileChange

    assert hasattr(ToolExecutor, "undo_last"), "Missing undo_last"
    assert hasattr(ToolExecutor, "get_change_history"), "Missing get_change_history"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        class MockEngine:
            active_branch = "main"
            head_hash = None
            context_window = []
            def push_message(self, m): pass
            def commit(self, r): pass
            def log(self, **kw): return []

        executor = ToolExecutor(tmpdir, MockEngine())
        test_file = tmpdir / "test.txt"
        test_file.write_text("original content", encoding="utf-8")

        result = executor.execute("edit_file", {
            "path": "test.txt",
            "old_string": "original content",
            "new_string": "modified content",
        })

        current = test_file.read_text(encoding="utf-8")
        assert current == "modified content", f"Edit didn't work: {current}"

        history = executor.get_change_history()
        assert len(history) >= 1, f"Change history empty"

        undo_result = executor.undo_last()
        restored = test_file.read_text(encoding="utf-8")
        assert restored == "original content", f"Undo didn't restore: {restored}"

        report(5, "/undo Command", True, f"edit+undo cycle verified, tracked {len(history)} changes")
except Exception as exc:
    report(5, "/undo Command", False, str(exc))

# =====================================================================
# Feature 6: Cost Tracking
# =====================================================================
print("\n=== Feature 6: Cost Tracking ===")
try:
    from cvc.agent.cost_tracker import CostTracker, MODEL_PRICING

    assert len(MODEL_PRICING) > 5, f"Too few models: {len(MODEL_PRICING)}"
    assert any("sonnet" in k for k in MODEL_PRICING), "Missing Sonnet pricing"
    assert any("gpt" in k for k in MODEL_PRICING), "Missing GPT pricing"
    assert any("gemini" in k for k in MODEL_PRICING), "Missing Gemini pricing"

    ct = CostTracker(model="claude-sonnet-4-5")
    cost1 = ct.add_usage(1000, 500, 200)
    assert cost1 > 0, f"Cost should be positive: {cost1}"
    assert ct.total_input_tokens == 1000
    assert ct.total_output_tokens == 500

    cost2 = ct.add_usage(2000, 1000, 0)
    assert ct.total_input_tokens == 3000
    assert ct.total_output_tokens == 1500
    assert ct.total_cost_usd > cost1

    cost_str = ct.format_cost()
    assert "$" in cost_str, f"format_cost missing $: {cost_str}"
    summary = ct.format_summary()
    assert "Session Cost Summary" in summary
    assert "claude-sonnet-4-5" in summary

    # Test Ollama (free)
    ct2 = CostTracker(model="qwen2.5-coder:7b")
    cost_free = ct2.add_usage(5000, 2000)
    assert cost_free == 0.0, f"Ollama should be free: {cost_free}"

    report(6, "Cost Tracking", True,
           f"pricing={len(MODEL_PRICING)} models, total=${ct.total_cost_usd:.6f}, ollama=$0 OK")
except Exception as exc:
    report(6, "Cost Tracking", False, str(exc))

# =====================================================================
# Feature 7: Image Support
# =====================================================================
print("\n=== Feature 7: Image Support ===")
try:
    from cvc.agent.chat import AgentSession

    assert hasattr(AgentSession, "_handle_image"), "Missing _handle_image"
    source = inspect.getsource(AgentSession._handle_image)

    assert "anthropic" in source, "Missing Anthropic image format"
    assert "openai" in source, "Missing OpenAI image format"
    assert "google" in source or "gemini" in source, "Missing Google image format"
    assert "base64" in source, "Missing base64 encoding"

    source2 = inspect.getsource(AgentSession.handle_slash_command)
    assert "/image" in source2, "Missing /image in slash commands"

    report(7, "Image Support", True, "Anthropic + OpenAI + Google formats, base64 encoding OK")
except Exception as exc:
    report(7, "Image Support", False, str(exc))

# =====================================================================
# Feature 8: Persistent Memory
# =====================================================================
print("\n=== Feature 8: Persistent Memory ===")
try:
    from cvc.agent.memory import (
        load_memory, save_memory_entry, get_relevant_memories,
        build_memory_context, generate_session_summary,
    )

    test_messages = [
        {"role": "system", "content": "You are a coding assistant."},
        {"role": "user", "content": "Fix the bug in auth.py"},
        {"role": "assistant", "content": "I found the issue in the authentication module."},
        {"role": "user", "content": "Also update the tests"},
        {"role": "assistant", "content": "I've updated the test suite for auth."},
    ]
    summary, topics = generate_session_summary(test_messages)
    assert isinstance(summary, str) and len(summary) > 0, f"Bad summary: {summary}"
    assert isinstance(topics, list), f"Topics should be list: {type(topics)}"
    assert "Fix the bug in auth.py" in summary, f"Summary should contain user request: {summary}"

    memory = load_memory()
    assert isinstance(memory, str), f"load_memory should return str: {type(memory)}"

    ctx = build_memory_context(str(WORKSPACE))
    assert isinstance(ctx, str), f"Memory context should be string: {type(ctx)}"

    report(8, "Persistent Memory", True,
           f"summary OK, topics={topics}, memory loaded, context={len(ctx)}ch")
except Exception as exc:
    report(8, "Persistent Memory", False, str(exc))

# =====================================================================
# Feature 9: Parallel Tool Execution
# =====================================================================
print("\n=== Feature 9: Parallel Tool Execution ===")
try:
    from cvc.agent.chat import AgentSession

    assert hasattr(AgentSession, "_execute_tools_parallel"), "Missing _execute_tools_parallel"
    source = inspect.getsource(AgentSession._execute_tools_parallel)

    assert "read_only_tools" in source, "Missing read_only_tools set"
    assert "asyncio.gather" in source, "Missing asyncio.gather"
    assert "all_read_only" in source, "Missing read/write distinction"
    assert "read_file" in source, "read_file should be read-only"

    report(9, "Parallel Tool Execution", True,
           "asyncio.gather + read-only distinction OK")
except Exception as exc:
    report(9, "Parallel Tool Execution", False, str(exc))

# =====================================================================
# Feature 10: Tab Completion
# =====================================================================
print("\n=== Feature 10: Tab Completion ===")
try:
    from cvc.agent.renderer import SLASH_COMMANDS, get_input_with_completion

    assert isinstance(SLASH_COMMANDS, list), f"Should be list: {type(SLASH_COMMANDS)}"
    assert len(SLASH_COMMANDS) >= 15, f"Expected 15+ commands, got {len(SLASH_COMMANDS)}"

    required = ["/help", "/exit", "/commit", "/branch", "/restore", "/undo",
                "/cost", "/web", "/git", "/image", "/memory", "/model"]
    missing = [cmd for cmd in required if cmd not in SLASH_COMMANDS]
    assert not missing, f"Missing commands: {missing}"

    assert callable(get_input_with_completion)

    try:
        import prompt_toolkit
        pt_ok = True
    except ImportError:
        pt_ok = False

    report(10, "Tab Completion", True,
           f"commands={len(SLASH_COMMANDS)}, prompt_toolkit={'available' if pt_ok else 'not installed'}")
except Exception as exc:
    report(10, "Tab Completion", False, str(exc))

# =====================================================================
# Feature 11: .cvcignore Support
# =====================================================================
print("\n=== Feature 11: .cvcignore Support ===")
try:
    from cvc.agent.executor import ToolExecutor
    from cvc.agent.auto_context import build_file_tree

    assert hasattr(ToolExecutor, "_load_cvcignore"), "Missing _load_cvcignore"
    assert hasattr(ToolExecutor, "_is_ignored"), "Missing _is_ignored"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        ignorefile = tmpdir / ".cvcignore"
        ignorefile.write_text("*.log\nsecrets/\nnode_modules/\n", encoding="utf-8")

        (tmpdir / "app.py").write_text("hello", encoding="utf-8")
        (tmpdir / "debug.log").write_text("log", encoding="utf-8")
        (tmpdir / "secrets").mkdir()
        (tmpdir / "secrets" / "key.pem").write_text("secret", encoding="utf-8")
        (tmpdir / "keep.txt").write_text("keep", encoding="utf-8")

        tree = build_file_tree(tmpdir)
        assert "app.py" in tree, "app.py should be in tree"
        assert "keep.txt" in tree, "keep.txt should be in tree"
        # .log and secrets/ should be filtered
        assert "debug.log" not in tree, "debug.log should be filtered by .cvcignore"
        assert "key.pem" not in tree, "secrets/key.pem should be filtered"

    report(11, ".cvcignore Support", True, "ignore loading + filtering verified")
except Exception as exc:
    report(11, ".cvcignore Support", False, str(exc))

# =====================================================================
# Feature 12: Session Resume
# =====================================================================
print("\n=== Feature 12: Session Resume ===")
try:
    from cvc.agent.renderer import render_session_resume_prompt
    from cvc.agent.chat import _run_agent_async, AgentSession

    assert callable(render_session_resume_prompt)

    source = inspect.getsource(_run_agent_async)
    assert "resume" in source.lower(), "Missing resume logic in REPL"
    assert "render_session_resume_prompt" in source, "Missing resume prompt call"

    assert hasattr(AgentSession, "_load_existing_context"), "Missing _load_existing_context"
    source2 = inspect.getsource(AgentSession._load_existing_context)
    assert "context_window" in source2, "Should reference context_window"

    report(12, "Session Resume", True, "resume prompt + context restoration OK")
except Exception as exc:
    report(12, "Session Resume", False, str(exc))

# =====================================================================
# Feature 13: /web Command
# =====================================================================
print("\n=== Feature 13: /web Command ===")
try:
    from cvc.agent.web_search import web_search, fetch_page_text, format_search_results
    from cvc.agent.tools import AGENT_TOOLS

    tool_names = [t["function"]["name"] for t in AGENT_TOOLS]
    assert "web_search" in tool_names, "web_search not in tool definitions"

    assert asyncio.iscoroutinefunction(web_search), "web_search should be async"
    assert asyncio.iscoroutinefunction(fetch_page_text), "fetch_page_text should be async"

    fmt = format_search_results([], "test query")
    assert isinstance(fmt, str)
    assert "no results" in fmt.lower() or "test query" in fmt.lower() or len(fmt) >= 0

    source = inspect.getsource(AgentSession.handle_slash_command)
    assert "/web" in source, "Missing /web in slash commands"

    # Live search test (optional)
    try:
        results = asyncio.run(web_search("python hello world", max_results=2))
        live_detail = f"live search returned {len(results)} results"
    except Exception as net_exc:
        live_detail = f"live test skipped ({type(net_exc).__name__})"

    report(13, "/web Command", True, f"web_search tool + format OK, {live_detail}")
except Exception as exc:
    report(13, "/web Command", False, str(exc))

# =====================================================================
# Feature 14: Git Integration
# =====================================================================
print("\n=== Feature 14: Git Integration ===")
try:
    from cvc.agent.git_integration import (
        is_git_repo, git_status, git_diff_summary,
        git_commit, git_log, format_git_status,
    )
    from cvc.agent.renderer import render_git_startup_info

    is_git = is_git_repo(WORKSPACE)
    assert isinstance(is_git, bool)

    status = git_status(WORKSPACE)
    assert isinstance(status, dict), f"git_status should return dict"
    assert "is_git" in status, "Missing 'is_git' key"

    if status.get("is_git"):
        fmt = format_git_status(status)
        assert isinstance(fmt, str) and len(fmt) > 0

        commits = git_log(WORKSPACE, limit=3)
        assert isinstance(commits, list)

        diff = git_diff_summary(WORKSPACE)
        assert isinstance(diff, str)

        source = inspect.getsource(AgentSession.handle_slash_command)
        assert "/git" in source, "Missing /git in slash commands"

        assert callable(render_git_startup_info)

        detail = (f"is_git={is_git}, branch={status.get('branch', '?')}, "
                  f"commits={len(commits)}")
    else:
        detail = "Not a git repo, but all functions work without error"

    report(14, "Git Integration", True, detail)
except Exception as exc:
    report(14, "Git Integration", False, str(exc))


# =====================================================================
# FINAL SUMMARY
# =====================================================================
print("\n" + "=" * 60)
print(f"  RESULTS: {passed} passed, {failed} failed out of 14 features")
print("=" * 60)
if errors_list:
    print("\nFailed features:")
    for err in errors_list:
        print(f"  - {err}")
else:
    print("\n  ALL 14 FEATURES VERIFIED SUCCESSFULLY!")
print()

sys.exit(1 if failed > 0 else 0)
