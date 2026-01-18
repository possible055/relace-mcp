"""Channel-specific prompt templates.

Channels do NOT use report_back - their findings are collected automatically
by the merger agent. These prompts exclude report_back references to avoid
model confusion on the final turn.
"""

CHANNEL_USER_PROMPT_TEMPLATE = """<repository>/repo</repository>

<user_query>
{query}
</user_query>

<task>
Explore the codebase using your specialized tools.
You have LIMITED turns. Call 4-12 tools in PARALLEL each turn.
Your findings will be collected automatically - do NOT use report_back.
</task>"""

CHANNEL_TURN_HINT_TEMPLATE = (
    """<status turn="{turn}/{max_turns}" context="{chars_pct}%">{instruction}</status>"""
)

CHANNEL_TURN_INSTRUCTIONS: dict[str, str] = {
    "normal": "",
    "final": "⚠️ FINAL TURN. Make your most important tool calls now.",
}
