#!/usr/bin/env python3
"""
Conversation manager and parser for Antigravity (AGY) sessions.
Reads brain transcripts from ~/.gemini/antigravity-cli/brain/
and provides structured conversation history for the assistant.
"""
import os
import json
import re
import glob
from datetime import datetime

BRAIN_DIR = os.path.expanduser("~/.gemini/antigravity-cli/brain")

def clean_user_text(raw: str) -> str:
    """Extract clean user voice request, stripping metadata and system prompts."""
    if not raw:
        return ""

    # Strip metadata and system tags
    raw = re.sub(r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"<USER_SETTINGS_CHANGE>.*?</USER_SETTINGS_CHANGE>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"<SYSTEM_MESSAGE>.*?</SYSTEM_MESSAGE>", "", raw, flags=re.DOTALL)

    # Extract user request content
    m_req = re.search(r"<USER_REQUEST>\s*(.*?)\s*(?:</USER_REQUEST>|$)", raw, re.DOTALL)
    text = m_req.group(1) if m_req else raw

    # Check for voice prompt template quotes (Spanish or English)
    m_voice = re.search(r"(?:Instrucci[oó]n de voz|User voice instruction)[^:]*:\s*[\x27\"\x60]([^\x27\"\x60]+)[\x27\"\x60]", text, re.IGNORECASE)
    if m_voice:
        return m_voice.group(1).strip()

    # Strip mandatory rules and action instructions if leaked into text
    text = re.sub(r"(?:MANDATORY RULES|REGLAS OBLIGATORIAS|Si te pide realizar una acci[oó]n).*$", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()

def get_all_conversations(active_conv_id: str = "", limit: int = 60):
    """
    Returns a sorted list of conversation summaries (most recent first).
    """
    if not os.path.isdir(BRAIN_DIR):
        return []

    dirs = glob.glob(os.path.join(BRAIN_DIR, "*"))
    dirs = [d for d in dirs if os.path.isdir(d)]
    dirs.sort(key=os.path.getmtime, reverse=True)

    conversations = []
    for d in dirs[:limit]:
        conv_id = os.path.basename(d)
        transcript_path = os.path.join(d, ".system_generated", "logs", "transcript.jsonl")
        if not os.path.exists(transcript_path):
            continue

        mtime = os.path.getmtime(transcript_path)
        dt = datetime.fromtimestamp(mtime)
        date_str = dt.strftime("%d/%m/%Y %H:%M:%S")

        first_prompt = ""
        last_prompt = ""
        last_reply = ""
        turn_count = 0
        tools_set = set()

        try:
            with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except Exception:
                        continue

                    etype = entry.get("type")
                    if etype == "USER_INPUT":
                        turn_count += 1
                        cleaned = clean_user_text(entry.get("content", ""))
                        if not first_prompt:
                            first_prompt = cleaned
                        last_prompt = cleaned
                    elif etype == "PLANNER_RESPONSE":
                        content = entry.get("content", "")
                        if content:
                            last_reply = content.strip()
                        for tc in entry.get("tool_calls", []):
                            if isinstance(tc, dict) and tc.get("name"):
                                tools_set.add(tc["name"])
        except Exception:
            continue

        if turn_count == 0 and not first_prompt:
            continue

        title = first_prompt if first_prompt else f"Conversación {conv_id[:8]}"
        if len(title) > 65:
            title = title[:62] + "..."

        conversations.append({
            "id": conv_id,
            "date_str": date_str,
            "timestamp": mtime,
            "turn_count": turn_count,
            "title": title,
            "last_user": last_prompt,
            "last_reply": last_reply[:120] if last_reply else "",
            "tools_used": list(tools_set),
            "is_active": (conv_id == active_conv_id)
        })

    return conversations

list_conversations = get_all_conversations

def get_conversation_turns(conv_id: str):
    """
    Parses full turn-by-turn history of a specific conversation ID.
    Returns list of dicts with user message, actions (tools), and assistant response.
    """
    transcript_path = os.path.join(BRAIN_DIR, conv_id, ".system_generated", "logs", "transcript.jsonl")
    if not os.path.exists(transcript_path):
        return []

    turns = []
    current_turn = None

    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue

                etype = entry.get("type")
                created_at = entry.get("created_at", "")

                time_str = ""
                if created_at:
                    try:
                        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        time_str = dt.astimezone().strftime("%H:%M:%S")
                    except Exception:
                        time_str = created_at

                if etype == "USER_INPUT":
                    current_turn = {
                        "user": clean_user_text(entry.get("content", "")),
                        "time": time_str,
                        "actions": [],
                        "reply": "",
                        "raw_user": entry.get("content", "")
                    }
                    turns.append(current_turn)
                elif current_turn is not None:
                    if entry.get("tool_calls"):
                        for tc in entry.get("tool_calls", []):
                            tname = tc.get("name", "tool")
                            args = tc.get("args", {})
                            cmd = args.get("CommandLine", "") if isinstance(args, dict) else ""
                            summary = args.get("toolSummary", "") if isinstance(args, dict) else ""
                            current_turn["actions"].append({
                                "name": tname,
                                "cmd": cmd,
                                "summary": summary
                            })
                    if etype == "PLANNER_RESPONSE" and entry.get("content"):
                        current_turn["reply"] = entry.get("content", "").strip()
    except Exception as e:
        return [{"user": f"Error leyendo transcripción: {e}", "time": "", "actions": [], "reply": ""}]

    return turns

def set_active_conversation_id(config_file: str, new_conv_id: str):
    lines = []
    found = False
    if os.path.exists(config_file):
        with open(config_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("ACTIVE_CONVERSATION_ID="):
                    lines.append(f'ACTIVE_CONVERSATION_ID="{new_conv_id}"\n')
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f'ACTIVE_CONVERSATION_ID="{new_conv_id}"\n')

    with open(config_file, "w", encoding="utf-8") as f:
        f.writelines(lines)

def get_conversation_detail(conv_id: str):
    """Returns detailed object with title, turns and executive summary."""
    turns = get_conversation_turns(conv_id)
    title = turns[0]["user"] if (turns and turns[0].get("user")) else f"Conversación {conv_id[:8]}"
    if len(title) > 65:
        title = title[:62] + "..."

    # Extract unique tools and latest exchange
    tools_used = []
    for t in turns:
        for a in t.get("actions", []):
            name = a.get("name")
            if name and name not in tools_used:
                tools_used.append(name)

    last_user = turns[-1].get("user", "") if turns else ""
    last_reply = turns[-1].get("reply", "") if turns else ""
    start_time = turns[0].get("time", "") if turns else ""
    last_time = turns[-1].get("time", "") if turns else ""

    return {
        "id": conv_id,
        "title": title,
        "turns": turns,
        "summary": {
            "total_turns": len(turns),
            "start_time": start_time,
            "last_time": last_time,
            "last_user": last_user,
            "last_reply": last_reply,
            "tools_used": tools_used
        }
    }

def reset_active_session():
    import uuid
    new_id = str(uuid.uuid4())
    proj_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg_file = os.path.join(proj_dir, "config", "config.env")
    set_active_conversation_id(cfg_file, new_id)
    return new_id

def delete_conversation(conv_id: str) -> bool:
    import shutil
    conv_dir = os.path.join(BRAIN_DIR, conv_id)
    if os.path.isdir(conv_dir):
        try:
            shutil.rmtree(conv_dir)
            return True
        except Exception:
            return False
    return False

def export_conversation_markdown(conv_id: str) -> str:
    detail = get_conversation_detail(conv_id)
    md = [f"# Conversación Jarvis: {detail['title']}\n"]
    md.append(f"- ID de Sesión: `{conv_id}`")
    md.append(f"- Total de Turnos: {len(detail['turns'])}\n---\n")

    for i, turn in enumerate(detail["turns"], 1):
        time_tag = f" ({turn['time']})" if turn.get("time") else ""
        md.append(f"### Turno {i}{time_tag}")
        md.append(f"**Usuario:**\n{turn.get('user', '')}\n")

        actions = turn.get("actions", [])
        if actions:
            md.append("**Herramientas ejecutadas:**")
            for act in actions:
                md.append(f"- `{act['name']}`: {act.get('summary') or act.get('cmd')}")
            md.append("")

        reply = turn.get("reply", "")
        if reply:
            md.append(f"**Jarvis:**\n{reply}\n")
        md.append("---\n")

    return "\n".join(md)

def set_live_idle(reason: str = ""):
    live_file = "/tmp/nobara_assistant_live.json"
    try:
        import time
        with open(live_file, "w", encoding="utf-8") as f:
            json.dump({
                "status": "IDLE",
                "current_action": reason or "En reposo",
                "updated_at": time.time()
            }, f)
    except Exception:
        pass
