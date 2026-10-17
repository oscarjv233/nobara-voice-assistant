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
    """Extract clean user voice request from AGY's prompt wrapping."""
    if not raw:
        return ""
    # Strip <USER_REQUEST> ... </USER_REQUEST>
    m = re.search(r'<USER_REQUEST>\s*(.*?)\s*(?:</USER_REQUEST>|$)', raw, re.DOTALL)
    text = m.group(1) if m else raw

    # Check for voice prompt template
    voice_m = re.search(r"Instrucción de voz[^:]*:\s*'([^']*)'", text)
    if voice_m:
        return voice_m.group(1).strip()
    
    # Strip any remaining XML-like tags
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()

def get_all_conversations(active_conv_id: str = "", limit: int = 60):
    """
    Returns a sorted list of conversation summaries (most recent first).
    """
    if not os.path.isdir(BRAIN_DIR):
        return []

    dirs = glob.glob(os.path.join(BRAIN_DIR, "*"))
    # Filter only valid directories
    dirs = [d for d in dirs if os.path.isdir(d)]
    # Sort by mtime descending
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
        last_reply = ""
        turn_count = 0

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
                        if not first_prompt:
                            first_prompt = clean_user_text(entry.get("content", ""))
                    elif etype == "PLANNER_RESPONSE" and entry.get("content"):
                        last_reply = entry.get("content", "").strip()
        except Exception:
            continue

        if turn_count == 0 and not first_prompt:
            continue

        conversations.append({
            "id": conv_id,
            "date_str": date_str,
            "timestamp": mtime,
            "turn_count": turn_count,
            "title": first_prompt if first_prompt else f"Conversación {conv_id[:8]}",
            "last_reply": last_reply[:120] if last_reply else "",
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
                
                # Format ISO timestamp nicely if present
                time_str = ""
                if created_at:
                    try:
                        # e.g. 2026-10-17T17:08:02Z
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
                    # Collect tool calls
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
    """Update ACTIVE_CONVERSATION_ID in config.env safely."""
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
