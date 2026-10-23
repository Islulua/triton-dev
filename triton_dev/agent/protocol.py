from triton_dev.common.contracts import ToolError

TYPES = {"query", "ask_user", "finish"}


def validate(message, task_id, turn, known_evidence):
    if not isinstance(message, dict):
        raise ToolError("MODEL_PROTOCOL_ERROR", "Message must be an object")
    allowed = {"schema_version", "task_id", "turn_id", "type", "action_id", "args",
               "evidence_ids", "conclusion", "question"}
    if set(message) - allowed:
        raise ToolError("MODEL_PROTOCOL_ERROR", "Unexpected fields")
    if (type(message.get("schema_version")) is not int or message.get("schema_version") != 1
            or message.get("task_id") != task_id or type(message.get("turn_id")) is not int
            or message.get("turn_id") != turn or not isinstance(message.get("type"), str)
            or message.get("type") not in TYPES):
        raise ToolError("MODEL_PROTOCOL_ERROR", "Invalid schema, task, turn or type")
    refs = message.get("evidence_ids", [])
    if not isinstance(refs, list) or any(not isinstance(x, str) or x not in known_evidence for x in refs):
        raise ToolError("UNKNOWN_EVIDENCE", "Model referenced evidence that does not exist")
    if message["type"] == "query":
        if set(message) - {"schema_version", "task_id", "turn_id", "type", "action_id", "args", "evidence_ids"}:
            raise ToolError("MODEL_PROTOCOL_ERROR", "Query has fields from another action type")
        if message.get("action_id") != "env.sdk.list" or message.get("args") != {}:
            raise ToolError("ACTION_NOT_ALLOWED", "Only the registered read-only list query is supported in v0.1")
    elif message["type"] == "ask_user":
        if set(message) - {"schema_version", "task_id", "turn_id", "type", "question", "evidence_ids"}:
            raise ToolError("MODEL_PROTOCOL_ERROR", "Question has fields from another action type")
        if not isinstance(message.get("question"), str) or not message["question"].strip():
            raise ToolError("MODEL_PROTOCOL_ERROR", "Question required")
    else:
        if set(message) - {"schema_version", "task_id", "turn_id", "type", "conclusion", "evidence_ids"}:
            raise ToolError("MODEL_PROTOCOL_ERROR", "Finish has fields from another action type")
        # No experiments are offered by this read-only scripted controller.
        if message.get("conclusion") != "insufficient_evidence":
            raise ToolError("FINISH_REJECTED", "Read-only queries cannot prove regression attribution")
    return message
