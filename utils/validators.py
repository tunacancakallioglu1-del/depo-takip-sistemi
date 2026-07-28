# -*- coding: utf-8 -*-
"""Validasyon yardımcıları"""

from datetime import datetime


def validate_required_fields(row, required_fields):
    missing = [field for field in required_fields if str(row.get(field, '')).strip() == '']
    return missing


def validate_headers(actual_headers, expected_headers):
    actual = [str(h).strip() for h in actual_headers]
    return actual == expected_headers


def parse_excel_date(value):
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value

    text = str(value).strip()
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None
