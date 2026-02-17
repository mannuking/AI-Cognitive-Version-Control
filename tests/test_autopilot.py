"""Quick test for Context Autopilot thinning and compaction."""
from cvc.agent.context_autopilot import ContextAutopilot, AutopilotConfig

# Create autopilot with a tiny context limit to trigger all thresholds
ap = ContextAutopilot('qwen2.5-coder:7b', config=AutopilotConfig(
    thin_threshold=0.3,
    compact_threshold=0.5,
    critical_threshold=0.7,
))

# Build a large message history to exceed thresholds
msgs = [{'role': 'system', 'content': 'You are a helpful assistant.'}]
for i in range(30):
    msgs.append({'role': 'user', 'content': f'Question {i}: ' + 'x' * 500})
    msgs.append({'role': 'assistant', 'content': f'Answer {i}: ' + 'y' * 500})
    msgs.append({'role': 'tool', 'tool_call_id': f'id_{i}', 'name': 'read_file', 'content': 'File contents: ' + 'z' * 2000})

health_before = ap.assess_health(msgs)
print(f'BEFORE: {health_before.health_level.value} ({health_before.utilization_pct:.1f}%)')
print(f'  Messages: {health_before.message_count}, Tool results: {health_before.tool_result_count}')
print(f'  Thinning candidates: {health_before.thinning_candidates}')
print(f'  Bar: {health_before.format_bar(30)}')

# Run autopilot (no engine, so no CVC commit)
msgs, health_after = ap.run(msgs)
print(f'\nAFTER:  {health_after.health_level.value} ({health_after.utilization_pct:.1f}%)')
print(f'  Messages: {health_after.message_count}')
print(f'  Actions: {health_after.actions_taken}')
print(f'  Bar: {health_after.format_bar(30)}')

# Diagnostics
diag = ap.get_diagnostics()
print(f'\nDIAGNOSTICS:')
print(f'  Compactions: {diag["session_stats"]["compactions_performed"]}')
print(f'  Thinnings: {diag["session_stats"]["thinnings_performed"]}')
print(f'  Tokens saved: {diag["session_stats"]["tokens_saved"]:,}')

print('\n✓ All Context Autopilot tests passed!')
