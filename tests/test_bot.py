from nepremicnine_bot.bot import parse_note_command



def test_parse_note_command_with_schedule():
    command = "/note 1111111 viewing_scheduled 2026-07-05T18:00 inspection booked"

    parsed = parse_note_command(command)

    assert parsed["site_id"] == "1111111"
    assert parsed["status"] == "viewing_scheduled"
    assert parsed["scheduled_for"] == "2026-07-05T18:00"
    assert parsed["note_text"] == "inspection booked"
