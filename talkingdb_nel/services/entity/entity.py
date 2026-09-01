from talkingdb_nel.services.bulk import parse_bulk_rows
from talkingdb_nel.services.namespace.registry import NamespaceBundle
from talkingdb_nel.services.symbolic.notag import NoTag


class EntityNotFoundError(Exception):
    """Raised when a referenced entity_id does not exist."""


class EntityAlreadyExistsError(Exception):
    """Raised when creating an entity_id that already exists."""


class SurfaceTextAlreadyExistsError(Exception):
    """Raised when adding a surface text an entity already has."""


class FactNotFoundError(Exception):
    """Raised when a referenced fact_id does not exist."""


class RegexRuleNotFoundError(Exception):
    """Raised when a referenced regex pattern does not exist for an entity."""


def index_entity(bundle: NamespaceBundle, entity: dict):
    bundle.word_matcher.load([entity])
    bundle.phrase_matcher.load([entity])


def create_entity(
    bundle: NamespaceBundle,
    entity_id: str,
    label: str | None = None,
    surface_texts: list[str] | None = None,
) -> dict:
    if bundle.entity_model.has_entity(entity_id):
        raise EntityAlreadyExistsError(entity_id)

    surface_texts = list(surface_texts or [])
    resolved_label = label or entity_id

    bundle.entity_model.add_entity(
        entity_id=entity_id,
        label=resolved_label,
        surface_texts=surface_texts,
    )
    bundle.entity_model.save(bundle.entity_conn)

    index_entity(bundle, {"entity_id": entity_id, "surface_texts": surface_texts})

    return {
        "entity_id": entity_id,
        "label": resolved_label,
        "surface_texts": surface_texts,
    }


def bulk_create_entities(bundle: NamespaceBundle, format: str, content: str) -> dict:
    rows = parse_bulk_rows(format, content)

    created = 0
    errors = []

    for index, row in enumerate(rows):
        try:
            entity_id = row["entity_id"]
            label = row.get("label") or None
            surface_texts_raw = row.get("surface_texts") or []

            if isinstance(surface_texts_raw, str):
                surface_texts = [
                    text.strip()
                    for text in surface_texts_raw.split("|")
                    if text.strip()
                ]
            else:
                surface_texts = list(surface_texts_raw)

            create_entity(
                bundle,
                entity_id=entity_id,
                label=label,
                surface_texts=surface_texts,
            )
            created += 1
        except EntityAlreadyExistsError as exc:
            errors.append({"row": index, "error": f"Entity '{exc}' already exists"})
        except (KeyError, TypeError, ValueError) as exc:
            errors.append({"row": index, "error": str(exc)})

    return {"created": created, "errors": errors}


def get_entity(bundle: NamespaceBundle, entity_id: str) -> dict | None:
    entity = bundle.entity_model.get_entity(entity_id)

    if entity is None:
        return None

    return {
        "entity_id": entity["id"],
        "label": entity["label"],
        "surface_texts": entity["surface_texts"],
    }


def list_entities(bundle: NamespaceBundle) -> list[dict]:
    return [
        {
            "entity_id": entity["id"],
            "label": entity["label"],
            "surface_texts": entity["surface_texts"],
        }
        for entity in bundle.entity_model.iter_entities()
    ]


def add_surface_text(
    bundle: NamespaceBundle, entity_id: str, surface_text: str
) -> dict:
    entity = bundle.entity_model.get_entity(entity_id)

    if entity is None:
        raise EntityNotFoundError(entity_id)

    texts = entity["surface_texts"]

    if surface_text in texts:
        raise SurfaceTextAlreadyExistsError(surface_text)

    texts.append(surface_text)

    bundle.entity_model.update_surface_texts(
        entity_id,
        texts,
    )
    bundle.entity_model.save(bundle.entity_conn)

    index_entity(
        bundle,
        {
            "entity_id": entity_id,
            "surface_texts": [surface_text],
        },
    )

    return {
        "entity_id": entity_id,
        "label": entity["label"],
        "surface_texts": texts,
    }


def update_entity(
    bundle: NamespaceBundle,
    entity_id: str,
    label: str | None = None,
    surface_texts: list[str] | None = None,
) -> dict:
    if not bundle.entity_model.has_entity(entity_id):
        raise EntityNotFoundError(entity_id)

    if label is not None:
        bundle.entity_model.update_label(entity_id, label)

    if surface_texts is not None:
        bundle.entity_model.update_surface_texts(entity_id, surface_texts)

    bundle.entity_model.save(bundle.entity_conn)

    if surface_texts is not None:
        # The fuzzy-match dictionary has no incremental removal - reindex
        # everything, same as after a rollback (see versioning.py).
        from talkingdb_nel.services.namespace.versioning import rebuild_dictionary

        rebuild_dictionary(bundle)

    return get_entity(bundle, entity_id)


def delete_entity(bundle: NamespaceBundle, entity_id: str) -> None:
    if not bundle.entity_model.has_entity(entity_id):
        raise EntityNotFoundError(entity_id)

    bundle.entity_model.remove_entity(entity_id)
    bundle.entity_model.save(bundle.entity_conn)

    from talkingdb_nel.services.namespace.versioning import rebuild_dictionary

    rebuild_dictionary(bundle)


def create_fact(
    bundle: NamespaceBundle,
    source: str,
    predicate: str,
    target: str,
    **attributes,
) -> dict:
    fact_id = bundle.entity_model.add_fact(
        source=source,
        target=target,
        predicate=predicate,
        **attributes,
    )
    bundle.entity_model.save(bundle.entity_conn)

    return {
        "id": fact_id,
        "source": source,
        "target": target,
        "predicate": predicate,
        **attributes,
    }


def get_fact(bundle: NamespaceBundle, fact_id: str) -> dict | None:
    return bundle.entity_model.get_fact(fact_id)


def list_facts(bundle: NamespaceBundle) -> list[dict]:
    return list(bundle.entity_model.iter_facts())


def update_fact(
    bundle: NamespaceBundle,
    fact_id: str,
    predicate: str | None = None,
    attributes: dict | None = None,
) -> dict:
    existing = bundle.entity_model.get_fact(fact_id)

    if existing is None:
        raise FactNotFoundError(fact_id)

    source = existing["source"]
    target = existing["target"]
    new_predicate = existing["predicate"] if predicate is None else predicate

    if attributes is None:
        attributes = {
            key: value
            for key, value in existing.items()
            if key not in {"id", "source", "target", "predicate"}
        }

    bundle.entity_model.remove_fact(fact_id)
    bundle.entity_model.add_fact(
        source=source,
        target=target,
        predicate=new_predicate,
        fact_id=fact_id,
        **attributes,
    )
    bundle.entity_model.save(bundle.entity_conn)

    return {
        "id": fact_id,
        "source": source,
        "target": target,
        "predicate": new_predicate,
        **attributes,
    }


def delete_fact(bundle: NamespaceBundle, fact_id: str) -> None:
    if bundle.entity_model.get_fact(fact_id) is None:
        raise FactNotFoundError(fact_id)

    bundle.entity_model.remove_fact(fact_id)
    bundle.entity_model.save(bundle.entity_conn)


def _suggestion_parts(suggestion):
    if isinstance(suggestion, tuple):
        text, (_, distance) = suggestion
        return text, distance

    return suggestion.term, suggestion.distance


def _resolve_entities(bundle: NamespaceBundle, suggestions):
    """
    Resolve raw matcher suggestions (surface text + edit distance) to the
    entity `entity_id`(s) they were trained under.
    """

    resolved = []
    seen_ids = set()

    for suggestion in suggestions:
        text, _ = _suggestion_parts(suggestion)

        for entity in bundle.entity_model.get_entities_by_surface_text(text):
            if entity["id"] in seen_ids:
                continue

            seen_ids.add(entity["id"])

            resolved.append(
                {
                    "entity_id": entity["id"],
                    "label": entity["label"],
                    "surface_text": text,
                }
            )

    return resolved


MAX_FUZZY_WINDOW_WORDS = 4

# Windows shorter than this keep the old 1-edit budget - at distance 2 a
# two/three-character window reaches almost any short surface text
# ("to" is 2 edits from "goa"), causing false positives.
TWO_EDIT_MIN_LENGTH = 5


def _window_edit_distance(window_text: str, word_correction: bool) -> int:
    if not word_correction:
        return 0
    return 2 if len(window_text) >= TWO_EDIT_MIN_LENGTH else 1


def _iter_no_tag_windows(message_text: str, no_tags: list[dict]):
    """
    Yield (start, end, text) windows over contiguous runs of no-tag tokens,
    joining up to MAX_FUZZY_WINDOW_WORDS whitespace-adjacent tokens so
    multi-word surface texts can be fuzzy-matched as a single phrase.
    """

    for i in range(len(no_tags)):
        start = no_tags[i]["index"][0]
        end = no_tags[i]["index"][1]

        yield start, end, message_text[start : end + 1]

        for j in range(i + 1, min(i + MAX_FUZZY_WINDOW_WORDS, len(no_tags))):
            gap = message_text[no_tags[j - 1]["index"][1] + 1 : no_tags[j]["index"][0]]

            if gap.strip():
                break

            end = no_tags[j]["index"][1]

            yield start, end, message_text[start : end + 1]


def _find_fuzzy_matches(
    bundle: NamespaceBundle, message_text: str, no_tags: list[dict], word_correction: bool = False,
):
    seen = set()

    for start, end, window_text in _iter_no_tag_windows(message_text, no_tags):
        max_edit_distance = _window_edit_distance(window_text, word_correction)
        for suggestion in bundle.phrase_matcher.get_suggestions(
            window_text,
            max_edit_distance=max_edit_distance,
        ):
            candidate, distance = _suggestion_parts(suggestion)

            seen_key = (start, end, candidate)

            if seen_key in seen:
                continue

            entities = _resolve_entities(bundle, [suggestion])

            if not entities:
                continue

            seen.add(seen_key)

            yield {
                "index": [start, end],
                "surface_text": message_text[start : end + 1],
                "corrected_text": candidate,
                "score": -distance,
                "entities": entities,
            }


def create_regex(bundle: NamespaceBundle, entity_id: str, regex: str) -> dict:
    if not bundle.entity_model.has_entity(entity_id):
        raise EntityNotFoundError(entity_id)

    bundle.regex_model.add_rule(
        entity_id,
        regex,
    )
    bundle.regex_model.save(bundle.regex_conn)

    return {"entity_id": entity_id, "regex": regex}


def list_regex_rules(bundle: NamespaceBundle, entity_id: str) -> list[str]:
    if not bundle.entity_model.has_entity(entity_id):
        raise EntityNotFoundError(entity_id)

    return [rule.pattern for rule in bundle.regex_model.rules.get(entity_id, [])]


def update_regex_rule(
    bundle: NamespaceBundle,
    entity_id: str,
    old_pattern: str,
    new_pattern: str,
) -> dict:
    try:
        bundle.regex_model.remove_pattern(entity_id, old_pattern)
    except (KeyError, ValueError) as exc:
        raise RegexRuleNotFoundError(old_pattern) from exc

    bundle.regex_model.add_rule(entity_id, new_pattern)
    bundle.regex_model.save(bundle.regex_conn)

    return {"entity_id": entity_id, "regex": new_pattern}


def delete_regex_rule(bundle: NamespaceBundle, entity_id: str, pattern: str) -> None:
    try:
        bundle.regex_model.remove_pattern(entity_id, pattern)
    except (KeyError, ValueError) as exc:
        raise RegexRuleNotFoundError(pattern) from exc

    bundle.regex_model.save(bundle.regex_conn)


def get_surface_texts(
    bundle: NamespaceBundle,
    message_text: str,
    word_correction: bool = False,
):
    universal_entities = bundle.surface_text_extractor.extract(
        message_text,
        [],
        word_correction=word_correction,
    )

    for entity in universal_entities:
        entity["entities"] = _resolve_entities(bundle, entity["entities"])

    universal_entities = [entity for entity in universal_entities if entity["entities"]]

    regex_entities = bundle.regex_controller.process(message_text)

    date_locations = set()

    for entity in regex_entities:
        if entity["rule"] == "Date_Regex":
            start, end = entity["index"]
            date_locations.update(range(start, end))

    filtered_regex = []

    for entity in regex_entities:
        if entity["rule"] == "Date_Regex":
            filtered_regex.append(entity)
            continue

        start, end = entity["index"]

        if not set(range(start, end)).intersection(date_locations):
            filtered_regex.append(entity)

    no_tags = NoTag.get_no_tags(
        message_text,
        universal_entities + regex_entities,
    )

    remaining_no_tags, lemmatized = bundle.lemmatizer.lemmatize(no_tags)

    seen = set()

    for chunk in lemmatized:
        start, end = chunk["index"]
        text = " ".join(chunk["lemmatized_tokens"])

        additional = bundle.phrase_matcher.get_suggestions(
            text,
            max_edit_distance=1 if word_correction else 0,
        )

        for suggestion in additional:
            candidate, distance = _suggestion_parts(suggestion)

            seen_key = (start, end, candidate)

            if seen_key in seen:
                continue

            entities = _resolve_entities(bundle, [suggestion])

            if not entities:
                continue

            universal_entities.append(
                {
                    "index": [start, end],
                    "surface_text": message_text[start : end + 1],
                    "corrected_text": candidate,
                    "score": -distance,
                    "entities": entities,
                }
            )

            seen.add(seen_key)

    # Always sweep, even with correction off - at distance 0 this is what finds correctly spelled 3+ word surface texts (the phrase cache above only builds single-word and adjacent-pair keys).
    for match in _find_fuzzy_matches(
        bundle, message_text, no_tags, word_correction=word_correction
    ):
        seen_key = tuple(match["index"]) + (match["corrected_text"],)

        if seen_key in seen:
            continue

        universal_entities.append(match)
        seen.add(seen_key)

    matched_ranges = [tuple(entity["index"]) for entity in universal_entities]

    remaining_no_tags = [
        tag
        for tag in remaining_no_tags
        if not any(
            tag["index"][0] <= end and start <= tag["index"][1]
            for start, end in matched_ranges
        )
    ]

    return {
        "universal_entities": universal_entities,
        "regex_entities": filtered_regex,
        "no_tag_entities": remaining_no_tags,
    }
