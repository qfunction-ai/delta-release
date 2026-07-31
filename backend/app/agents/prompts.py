"""Prompt-building helpers — skill/lesson prefixes and message extraction."""

import json

# Sentinel delimiter injected between skill prompt and user message.
# The history endpoint strips everything before this marker so the
# user sees their original message, not the skill prompt.
SKILL_PROMPT_END = "\n[//skill-context-end]\n"


def build_skill_prompt_prefix(skill_names: list[str]) -> str:
    """Build a short prompt prefix listing available skills.

    The actual skill content is injected inline by build_skill_inline_block().
    This prefix just tells the agent that skills are present and how to use them.
    """
    names_str = ", ".join(skill_names)
    return (
        f"You have the following skills available: {names_str}.\n"
        f"Their full instructions are provided below. Follow EVERY step in order.\n"
        f"\n"
        f"Rules for using skills:\n"
        f"1. When a skill is relevant, follow its steps exactly — do not skip or rearrange.\n"
        f"2. If a skill references tools you do not have, say so — do not guess.\n"
        f"3. After completing all steps in a skill, report your findings.\n"
        f"4. For general questions unrelated to a skill, respond directly.\n"
        f"5. A skill is provided for THIS message only. If the user's next message does not\n"
        f"   include skill context, the skill is not active — do not run skill steps.\n"
        f"6. NEVER stop mid-skill after a tool call returns. If a skill has multiple steps,\n"
        f"   you MUST continue to the next step immediately. Do not summarize and stop.\n"
        f"\n"
    )


def build_skill_inline_block(skills: list, skill_files: dict[str, list] | None = None) -> str:
    """Build the inline skill content block injected directly into the message.

    Each skill's SKILL.md content is included verbatim so the agent has
    the instructions in context without needing to search archival memory.

    If skill_files is provided, text files for each skill are appended
    after the skill content. skill_files maps skill_id -> list of
    (path, content_text) tuples.
    """
    blocks = []
    for skill in skills:
        content = getattr(skill, "content", None)
        if not content:
            continue
        block = (
            f"[Skill: {skill.name}]\n"
            f"Follow ALL steps below in order. Do not skip any step.\n"
            f"After each tool call, immediately proceed to the next step — do NOT stop.\n"
            f"---\n"
            f"{content}\n"
            f"---\n"
            f"End of skill: {skill.name}"
        )

        # Append text files for this skill
        if skill_files:
            files = skill_files.get(str(skill.id), [])
            for path, text in files:
                block += f"\n\n[Skill File: {skill.name}/{path}]\n---\n{text}\n---\nEnd of skill file: {path}"

        blocks.append(block)

    if not blocks:
        return ""

    return "\n\n".join(blocks) + SKILL_PROMPT_END


def build_skill_metadata_block(skills: list, skill_tool_names: dict[str, list[str]]) -> str:
    """Build a structured metadata block for skill state tracking.

    Args:
        skills: List of Skill objects
        skill_tool_names: Dict mapping skill_id (str) -> list of tool names

    Returns:
        JSON block wrapped in <skill_state> tags, or empty string if no
        skills have linked tools.
    """
    entries = []
    for skill in skills:
        tool_names = skill_tool_names.get(str(skill.id), [])
        if tool_names:
            entries.append(
                {
                    "skill_name": skill.name,
                    "required_tools": tool_names,
                }
            )
    if not entries:
        return ""
    return f"\n<skill_state>\n{json.dumps(entries, indent=2)}\n</skill_state>\n"


def build_lesson_prompt_prefix(lesson_count: int) -> str:
    """Build the prompt prefix that instructs an agent to load past lessons.

    Lessons are past execution experiences — what worked, what failed,
    and how to optimize. Unlike skills (mandatory steps), lessons are
    advisory guidance the agent should consider.
    """
    return (
        f"You have {lesson_count} execution lesson(s) from past runs available in your archival memory.\n"
        f"\n"
        f"These are past experiences from this workflow — successful strategies, failure recoveries, and efficiency tips.\n"
        f"Before taking action, search for relevant lessons:\n"
        f'  archival_memory_search(query="past experience", tags=["lessons"], tag_match_mode="any", top_k=5)\n'
        f"\n"
        f'Important: the tags parameter MUST be ["lessons"] — this is how lessons are tagged in your memory.\n'
        f"Lessons are advisory — learn from past successes and avoid repeated failures.\n"
        f"\n"
    )


def extract_message_parts(
    messages: list,
    include_reasoning: bool = False,
) -> tuple[str, str | None]:
    """Extract assistant output and reasoning from Letta response messages.

    Returns: (assistant_output, reasoning_output)
    """
    assistant_parts = []
    reasoning_parts = []
    for message in messages:
        msg_type = getattr(message, "message_type", "unknown")
        if msg_type == "assistant_message" and hasattr(message, "content") and message.content:
            assistant_parts.append(str(message.content))
        elif msg_type == "reasoning_message" and hasattr(message, "reasoning") and message.reasoning:
            reasoning_parts.append(str(message.reasoning))

    assistant_output = "\n".join(assistant_parts) if assistant_parts else None
    reasoning_output = "\n".join(reasoning_parts) if (include_reasoning and reasoning_parts) else None

    # Fallback: some models (e.g. thinking/reasoning models via Ollama) produce
    # only reasoning_message entries with no assistant_message. In that case,
    # promote the reasoning content to assistant_output so the user sees
    # something instead of a blank result.
    if assistant_output is None and reasoning_parts:
        assistant_output = "\n".join(reasoning_parts)
        reasoning_output = None

    return assistant_output, reasoning_output
