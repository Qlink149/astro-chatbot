#!/usr/bin/env python3
"""Rewrite birth_details.json with free-text place (no city dropdown)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "json" / "birth_details.json"

flow = {
    "version": "7.0",
    "screens": [
        {
            "id": "BIRTH_DETAILS",
            "terminal": True,
            "title": "Your Birth Details",
            "layout": {
                "type": "SingleColumnLayout",
                "children": [
                    {
                        "name": "flow_path",
                        "type": "Form",
                        "children": [
                            {
                                "type": "TextSubheading",
                                "text": (
                                    "Share date, birth time (or say you don't know), "
                                    "and place of birth as free text (city + state/country). "
                                    "If time is unknown, Lagna/ascendant and precise "
                                    "house-based timing can't be given — a meaningful Moon "
                                    "+ dasha reading is still possible."
                                ),
                            },
                            {
                                "type": "DatePicker",
                                "name": "birth_date",
                                "label": "Date of Birth",
                                "required": True,
                            },
                            {
                                "type": "TextInput",
                                "name": "birth_hour_input",
                                "label": "Hour of Birth (1-12)",
                                "helper-text": "Type the hour, e.g. 7. Skip if you don't know.",
                                "input-type": "number",
                                "min-chars": 1,
                                "max-chars": 2,
                                "required": False,
                            },
                            {
                                "type": "TextInput",
                                "name": "birth_minute_input",
                                "label": "Minute of Birth (0-59)",
                                "helper-text": "Type the minute, e.g. 32. Skip if you don't know.",
                                "input-type": "number",
                                "min-chars": 1,
                                "max-chars": 2,
                                "required": False,
                            },
                            {
                                "type": "RadioButtonsGroup",
                                "name": "birth_ampm",
                                "label": "AM or PM?",
                                "required": False,
                                "data-source": [
                                    {"id": "AM", "title": "AM (morning)"},
                                    {"id": "PM", "title": "PM (afternoon / evening)"},
                                ],
                            },
                            {
                                "type": "OptIn",
                                "name": "unknown_time",
                                "label": "I don't know my birth time",
                                "required": False,
                            },
                            {
                                "type": "TextInput",
                                "name": "birth_place",
                                "label": "Place of Birth",
                                "helper-text": "Type city and state/country, e.g. Udaipur Rajasthan",
                                "input-type": "text",
                                "min-chars": 2,
                                "max-chars": 80,
                                "required": True,
                            },
                            {
                                "type": "Footer",
                                "label": "Get My Reading",
                                "on-click-action": {
                                    "name": "complete",
                                    "payload": {
                                        "flow_kind": "birth_details",
                                        "birth_date": "${form.birth_date}",
                                        "birth_hour_input": "${form.birth_hour_input}",
                                        "birth_minute_input": "${form.birth_minute_input}",
                                        "birth_ampm": "${form.birth_ampm}",
                                        "unknown_time": "${form.unknown_time}",
                                        "birth_place": "${form.birth_place}",
                                    },
                                },
                            },
                        ],
                    }
                ],
            },
        }
    ],
}

path.write_text(json.dumps(flow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("wrote", path)
