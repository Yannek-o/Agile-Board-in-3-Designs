"""CSV export and import of backlog items (Excel-friendly: UTF-8 BOM, semicolon)."""

import csv
import io
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.backlog.models import BacklogItem
from apps.backlog.services import create_backlog_item

EXPORT_COLUMNS = (
    "ID", "Titel", "Typ", "Status", "Priorität", "Story Points", "Bearbeiter",
    "Sprint", "Release", "Labels", "Beschreibung",
)
COLUMN_ALIASES = {
    "title": ("titel", "title", "summary"),
    "item_type": ("typ", "type", "issue type"),
    "priority": ("priorität", "prioritaet", "priority"),
    "story_points": ("story points", "points", "punkte"),
    "assignee": ("bearbeiter", "assignee"),
    "description": ("beschreibung", "description"),
}
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
IMPORTABLE_TYPES = [
    choice for choice in BacklogItem.ItemType if choice != BacklogItem.ItemType.SUBTASK
]
MAX_IMPORT_ROWS = 500
MAX_IMPORT_BYTES = 1024 * 1024


def neutralise_formula(value) -> str:
    """Prevents spreadsheet programs from evaluating cell content as formula."""
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(FORMULA_PREFIXES) else text


def restore_formula(text: str) -> str:
    if text.startswith("'") and text[1:].startswith(FORMULA_PREFIXES):
        return text[1:]
    return text


def export_rows(items):
    yield EXPORT_COLUMNS
    for item in items:
        sprint_entries = getattr(item, "open_sprint_entries", [])
        yield [
            neutralise_formula(value)
            for value in (
                item.key,
                item.title,
                item.get_item_type_display(),
                item.project.status_label(item.status),
                item.get_priority_display(),
                item.story_points,
                item.assignee.username if item.assignee else "",
                ", ".join(entry.sprint.label for entry in sprint_entries),
                item.fix_version.name if item.fix_version_id else "",
                ", ".join(label.name for label in item.labels.all()),
                item.description,
            )
        ]


def write_csv(rows, stream) -> None:
    stream.write("\ufeff")
    writer = csv.writer(stream, delimiter=";", lineterminator="\r\n")
    writer.writerows(rows)


class CsvImportError(ValueError):
    """The file as a whole cannot be read."""


@dataclass
class ImportResult:
    created: list = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _choice_lookup(choices) -> dict[str, str]:
    lookup = {}
    for choice in choices:
        lookup[choice.value.lower()] = choice.value
        lookup[choice.label.lower()] = choice.value
    return lookup


TYPE_LOOKUP = _choice_lookup(IMPORTABLE_TYPES)
PRIORITY_LOOKUP = _choice_lookup(BacklogItem.Priority)


def read_rows(uploaded_file) -> list[tuple[int, dict]]:
    if uploaded_file.size > MAX_IMPORT_BYTES:
        raise CsvImportError("Die Datei ist größer als 1 MB.")
    raw = uploaded_file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    first_line = text.split("\n", 1)[0]
    delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = next(reader, None)
    if not header:
        raise CsvImportError("Die Datei ist leer.")
    columns = {}
    for index, name in enumerate(header):
        normalised = name.strip().lower()
        for field_name, aliases in COLUMN_ALIASES.items():
            if normalised in aliases and field_name not in columns:
                columns[field_name] = index
    if "title" not in columns:
        raise CsvImportError("Spalte „Titel“ fehlt.")
    rows = []
    for line in reader:
        if not any(cell.strip() for cell in line):
            continue
        row = {
            field_name: restore_formula(line[index].strip())
            if index < len(line) else ""
            for field_name, index in columns.items()
        }
        rows.append((reader.line_num, row))
    if len(rows) > MAX_IMPORT_ROWS:
        raise CsvImportError(f"Höchstens {MAX_IMPORT_ROWS} Zeilen pro Import.")
    return rows


def _parse_row(row: dict, members: dict) -> tuple[dict, list[str]]:
    fields, problems = {}, []
    title = row.get("title", "")
    if not title:
        problems.append("Titel fehlt")
    elif len(title) > 200:
        problems.append("Titel ist länger als 200 Zeichen")
    fields["title"] = title
    if row.get("item_type"):
        item_type = TYPE_LOOKUP.get(row["item_type"].lower())
        if item_type is None:
            problems.append(f"unbekannter Typ „{row['item_type']}“")
        fields["item_type"] = item_type
    if row.get("priority"):
        priority = PRIORITY_LOOKUP.get(row["priority"].lower())
        if priority is None:
            problems.append(f"unbekannte Priorität „{row['priority']}“")
        fields["priority"] = priority
    if row.get("story_points"):
        points = row["story_points"]
        if not points.isdigit() or int(points) > 100:
            problems.append(f"Story Points „{points}“ müssen 0–100 sein")
        else:
            fields["story_points"] = int(points)
    if row.get("assignee"):
        assignee = members.get(row["assignee"].lower())
        if assignee is None:
            problems.append(f"„{row['assignee']}“ ist kein Projektmitglied")
        fields["assignee"] = assignee
    fields["description"] = row.get("description", "")
    return {key: value for key, value in fields.items() if value is not None}, problems


def import_items(project, uploaded_file, actor) -> ImportResult:
    """Validates every row first; imports all rows or none."""
    result = ImportResult()
    rows = read_rows(uploaded_file)
    if not rows:
        result.errors.append("Die Datei enthält keine Einträge.")
        return result
    members = {
        membership.user.username.lower(): membership.user
        for membership in project.active_members()
    }
    parsed = []
    for line_number, row in rows:
        fields, problems = _parse_row(row, members)
        if problems:
            result.errors.append(f"Zeile {line_number}: {'; '.join(problems)}")
        parsed.append(fields)
    if result.errors:
        return result
    try:
        with transaction.atomic():
            for fields in parsed:
                result.created.append(
                    create_backlog_item(project=project, actor=actor, **fields)
                )
    except ValidationError as error:
        result.created = []
        result.errors.extend(error.messages)
    return result
