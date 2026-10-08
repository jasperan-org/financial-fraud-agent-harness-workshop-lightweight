from workshop.loop import assistant_message, budgeted_steps, call_tool, end_turn, start_turn

# TODO 9: write one pass of the loop below. start_turn, budgeted_steps and end_turn are given.
# Steps:
#   1. msg = chat(messages, tools=tool_schemas).choices[0].message
#   2. No msg.tool_calls: final = msg.content or "", then break.
#   3. Otherwise messages.append(assistant_message(msg)), then for each tc in msg.tool_calls append
#      {"role": "tool", "tool_call_id": tc.id, "content": call_tool(TOOLS, tc, step, verbose, offload)}.
def agent_turn(user_query, thread_id="default", max_iterations=8, budget_seconds=360.0, verbose=True):
    """Answer one question: alternate chat and call_tool until the model answers or the budget ends."""
    messages, tool_schemas, offload, started = start_turn(
        store, thread_id, user_query, SYSTEM_PROMPT, build_context, retrieve_tools, OFFLOAD_CHARS)
    final = ""
    for step in budgeted_steps(max_iterations, started, budget_seconds):
        # YOUR CODE HERE
        raise NotImplementedError("TODO 9: agent_turn dispatch loop")
    return end_turn(store, chat, thread_id, user_query, final, messages, started, verbose)
