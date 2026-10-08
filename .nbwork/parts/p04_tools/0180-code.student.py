from functools import partial

# TODO 8: implement tool_list_skills (keep the @register)
# Returns a JSON string: a list of {"name", "category", "description"}, best match first.
# Steps:
# 1. Select name, category, description from skillbox, ordered by the same VECTOR_DISTANCE
#    expression as retrieve_tools in 4.1, first :k rows.
# 2. Build the list of dicts; wt.lob_text(description) turns a CLOB into str.
# 3. Return json.dumps(list).
@register
def tool_list_skills(query: str, k: int = 5) -> str:
    """Search the skillbox semantically. Returns top-k skills (name + description)."""
    # YOUR CODE HERE
    raise NotImplementedError("TODO 8: tool_list_skills")

build_skill_manifest = partial(wt.skill_manifest, agent_conn, ONNX_EMBED_MODEL)   # build_skill_manifest(query, k=3)
