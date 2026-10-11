from workshop.loop import assistant_message, budgeted_steps, call_tool, end_turn, start_turn

def agent_turn(user_query, thread_id="default", max_iterations=8, budget_seconds=360.0, verbose=True):
    """Answer one question: alternate chat and call_tool until the model answers or the budget ends."""
    messages, tool_schemas, offload, started = start_turn(
        store, thread_id, user_query, SYSTEM_PROMPT, build_context, retrieve_tools, OFFLOAD_CHARS)
    final = ""
    for step in budgeted_steps(max_iterations, started, budget_seconds):
        msg = chat(messages, tools=tool_schemas).choices[0].message
        if not msg.tool_calls:      # the model answered: keep the text and stop looping
            final = msg.content or ""
            break
        # TODO 8 (the model asked for tools; write this branch, about 3 lines):
        # 1. messages.append(assistant_message(msg)): record the model's request first, so every tool result
        #    that follows has the matching call before it (the API rejects a result without its call).
        # 2. For each tc in msg.tool_calls, append one dict to messages with three keys:
        #      "role": "tool"            marks it as a tool result,
        #      "tool_call_id": tc.id     links it to the request it answers,
        #      "content": call_tool(TOOLS, tc, step, verbose, offload)   runs the tool, returns its result text.
        raise NotImplementedError("TODO 8: append assistant_message(msg), then one tool message per tc")
    return end_turn(store, chat, thread_id, user_query, final, messages, started, verbose)
