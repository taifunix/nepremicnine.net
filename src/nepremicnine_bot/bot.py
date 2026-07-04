def parse_note_command(command: str) -> dict[str, str]:
    _, site_id, status, scheduled_for, *note_parts = command.split()
    return {
        "site_id": site_id,
        "status": status,
        "scheduled_for": scheduled_for,
        "note_text": " ".join(note_parts),
    }
