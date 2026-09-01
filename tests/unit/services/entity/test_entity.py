import uuid
from types import SimpleNamespace

import pytest

from talkingdb_nel.services.entity import entity


def make_bundle(**overrides):
    defaults = {
        "namespace": "test",
        "dictionary": SimpleNamespace(clear=lambda: None),
        "entity_model": SimpleNamespace(
            has_entity=lambda entity_id: False,
            get_entity=lambda entity_id: None,
            add_entity=lambda **kwargs: None,
            update_surface_texts=lambda *args, **kwargs: None,
            update_label=lambda *args, **kwargs: None,
            remove_entity=lambda entity_id: None,
            add_fact=lambda **kwargs: "fact-1",
            get_fact=lambda fact_id: None,
            remove_fact=lambda fact_id: None,
            iter_facts=lambda: iter([]),
            iter_entities=lambda: iter([]),
            get_entities_by_surface_text=lambda text: [],
            save=lambda conn: None,
        ),
        "regex_model": SimpleNamespace(
            rules={},
            add_rule=lambda *args, **kwargs: None,
            remove_pattern=lambda *args, **kwargs: None,
            save=lambda conn: None,
        ),
        "word_matcher": SimpleNamespace(load=lambda docs: None),
        "phrase_matcher": SimpleNamespace(
            load=lambda docs: None,
            get_suggestions=lambda text, max_edit_distance=None: [],
        ),
        "lemmatizer": SimpleNamespace(lemmatize=lambda no_tags: (no_tags, [])),
        "regex_controller": SimpleNamespace(process=lambda text: []),
        "surface_text_extractor": SimpleNamespace(extract=lambda *args, **kwargs: []),
        "entity_conn": None,
        "regex_conn": None,
    }

    for key, value in overrides.items():
        if key in defaults and isinstance(value, SimpleNamespace):
            merged = vars(defaults[key]).copy()
            merged.update(vars(value))
            defaults[key] = SimpleNamespace(**merged)
        else:
            defaults[key] = value

    return SimpleNamespace(**defaults)


def test_index_entity():
    word_loaded = []
    phrase_loaded = []

    bundle = make_bundle(
        word_matcher=SimpleNamespace(load=lambda docs: word_loaded.extend(docs)),
        phrase_matcher=SimpleNamespace(load=lambda docs: phrase_loaded.extend(docs)),
    )

    e = {
        "entity_id": "Q1",
        "surface_texts": ["Apple", "Apple Inc"],
    }

    entity.index_entity(bundle, e)

    assert word_loaded == [e]
    assert phrase_loaded == [e]


def test_create_entity_success():
    bundle = make_bundle()

    result = entity.create_entity(
        bundle,
        "Q1",
        label="Apple",
        surface_texts=["Apple", "Apple Inc"],
    )

    assert result == {
        "entity_id": "Q1",
        "label": "Apple",
        "surface_texts": ["Apple", "Apple Inc"],
    }


def test_create_entity_defaults_label_to_entity_id():
    bundle = make_bundle()

    result = entity.create_entity(bundle, "Q1")

    assert result == {
        "entity_id": "Q1",
        "label": "Q1",
        "surface_texts": [],
    }


def test_bulk_create_entities_json():
    created_ids = []

    bundle = make_bundle(
        entity_model=SimpleNamespace(
            has_entity=lambda entity_id: False,
            add_entity=lambda entity_id, label, surface_texts: created_ids.append(
                entity_id
            ),
            save=lambda conn: None,
        )
    )

    content = (
        '[{"entity_id": "Q1", "label": "Apple", "surface_texts": ["Apple"]},'
        ' {"entity_id": "Q2", "surface_texts": ["Google"]}]'
    )

    result = entity.bulk_create_entities(bundle, "json", content)

    assert result == {"created": 2, "errors": []}
    assert created_ids == ["Q1", "Q2"]


def test_bulk_create_entities_csv_pipe_separated_surface_texts():
    captured = []

    bundle = make_bundle(
        entity_model=SimpleNamespace(
            has_entity=lambda entity_id: False,
            add_entity=lambda entity_id, label, surface_texts: captured.append(
                (entity_id, label, surface_texts)
            ),
            save=lambda conn: None,
        )
    )

    content = "entity_id,label,surface_texts\nQ1,Apple,Apple|Apple Inc\n"

    result = entity.bulk_create_entities(bundle, "csv", content)

    assert result == {"created": 1, "errors": []}
    assert captured == [("Q1", "Apple", ["Apple", "Apple Inc"])]


def test_bulk_create_entities_collects_per_row_errors():
    bundle = make_bundle(
        entity_model=SimpleNamespace(has_entity=lambda entity_id: True)
    )

    content = '[{"entity_id": "Q1"}]'

    result = entity.bulk_create_entities(bundle, "json", content)

    assert result["created"] == 0
    assert len(result["errors"]) == 1
    assert result["errors"][0]["row"] == 0


def test_bulk_create_entities_missing_entity_id_collected_as_error():
    bundle = make_bundle(
        entity_model=SimpleNamespace(has_entity=lambda entity_id: False)
    )

    content = '[{"label": "Apple"}]'

    result = entity.bulk_create_entities(bundle, "json", content)

    assert result["created"] == 0
    assert result["errors"] == [{"row": 0, "error": "'entity_id'"}]


def test_create_entity_already_exists():
    bundle = make_bundle(
        entity_model=SimpleNamespace(has_entity=lambda entity_id: True)
    )

    with pytest.raises(entity.EntityAlreadyExistsError):
        entity.create_entity(bundle, "Q1")


def test_get_entity_found():
    bundle = make_bundle(
        entity_model=SimpleNamespace(
            get_entity=lambda entity_id: {
                "id": entity_id,
                "label": "Apple",
                "surface_texts": ["Apple"],
            }
        )
    )

    assert entity.get_entity(bundle, "Q1") == {
        "entity_id": "Q1",
        "label": "Apple",
        "surface_texts": ["Apple"],
    }


def test_get_entity_missing():
    bundle = make_bundle()

    assert entity.get_entity(bundle, "Q1") is None


def test_list_entities():
    bundle = make_bundle(
        entity_model=SimpleNamespace(
            iter_entities=lambda: iter(
                [
                    {"id": "Q1", "label": "Apple", "surface_texts": ["Apple"]},
                    {"id": "Q2", "label": "Google", "surface_texts": ["Google"]},
                ]
            )
        )
    )

    assert entity.list_entities(bundle) == [
        {"entity_id": "Q1", "label": "Apple", "surface_texts": ["Apple"]},
        {"entity_id": "Q2", "label": "Google", "surface_texts": ["Google"]},
    ]


def test_add_surface_text_success():
    updated = {}

    bundle = make_bundle(
        entity_model=SimpleNamespace(
            get_entity=lambda _: {
                "label": "Apple",
                "surface_texts": ["Apple"],
            },
            update_surface_texts=lambda entity_id, texts: updated.update(
                {"id": entity_id, "texts": texts}
            ),
        )
    )

    result = entity.add_surface_text(bundle, "Q1", "Apple Inc")

    assert result == {
        "entity_id": "Q1",
        "label": "Apple",
        "surface_texts": ["Apple", "Apple Inc"],
    }

    assert updated["texts"] == ["Apple", "Apple Inc"]


def test_add_surface_text_missing_entity():
    bundle = make_bundle(entity_model=SimpleNamespace(get_entity=lambda _: None))

    with pytest.raises(entity.EntityNotFoundError):
        entity.add_surface_text(bundle, "Q1", "Apple")


def test_add_surface_text_duplicate():
    bundle = make_bundle(
        entity_model=SimpleNamespace(
            get_entity=lambda _: {"label": "Apple", "surface_texts": ["Apple"]}
        )
    )

    with pytest.raises(entity.SurfaceTextAlreadyExistsError):
        entity.add_surface_text(bundle, "Q1", "Apple")


def test_create_fact():
    called = {}

    bundle = make_bundle(
        entity_model=SimpleNamespace(
            add_fact=lambda **kwargs: called.update(kwargs) or "fact-42",
            save=lambda conn: None,
        )
    )

    result = entity.create_fact(bundle, "A", "KNOWS", "B", since=2025)

    assert result == {
        "id": "fact-42",
        "source": "A",
        "target": "B",
        "predicate": "KNOWS",
        "since": 2025,
    }

    assert called["source"] == "A"
    assert called["target"] == "B"
    assert called["predicate"] == "KNOWS"
    assert called["since"] == 2025


def test_get_fact_found():
    bundle = make_bundle(
        entity_model=SimpleNamespace(
            get_fact=lambda fact_id: {
                "id": fact_id,
                "source": "A",
                "target": "B",
                "predicate": "KNOWS",
            }
        )
    )

    assert entity.get_fact(bundle, "fact-1") == {
        "id": "fact-1",
        "source": "A",
        "target": "B",
        "predicate": "KNOWS",
    }


def test_get_fact_missing():
    bundle = make_bundle()

    assert entity.get_fact(bundle, "fact-1") is None


def test_list_facts():
    bundle = make_bundle(
        entity_model=SimpleNamespace(
            iter_facts=lambda: iter(
                [{"id": "fact-1", "source": "A", "target": "B", "predicate": "KNOWS"}]
            )
        )
    )

    assert entity.list_facts(bundle) == [
        {"id": "fact-1", "source": "A", "target": "B", "predicate": "KNOWS"}
    ]


def test_suggestion_parts_tuple():
    assert entity._suggestion_parts(("apple", (3, 1))) == ("apple", 1)


def test_resolve_entities_deduplicates_by_entity_id():
    bundle = make_bundle(
        entity_model=SimpleNamespace(
            get_entities_by_surface_text=lambda text: [
                {"id": "Q1", "label": "Apple", "surface_texts": ["Apple"]},
                {"id": "Q1", "label": "Apple", "surface_texts": ["Apple"]},
            ]
        )
    )

    resolved = entity._resolve_entities(bundle, [("apple", (1, 0))])

    assert resolved == [
        {"entity_id": "Q1", "label": "Apple", "surface_text": "apple"},
    ]


def test_resolve_entities_no_match():
    bundle = make_bundle()

    assert entity._resolve_entities(bundle, [("apple", (1, 0))]) == []


def test_get_surface_texts_attaches_entity_id_and_drops_unresolved():
    bundle = make_bundle(
        surface_text_extractor=SimpleNamespace(
            extract=lambda *args, **kwargs: [
                {
                    "index": [0, 4],
                    "surface_text": "apple",
                    "corrected_text": "apple",
                    "score": 0,
                    "entities": [("apple", (1, 0))],
                },
                {
                    "index": [10, 15],
                    "surface_text": "mango",
                    "corrected_text": "mango",
                    "score": 0,
                    "entities": [("mango", (1, 0))],
                },
            ]
        ),
        entity_model=SimpleNamespace(
            get_entities_by_surface_text=lambda text: (
                [{"id": "Q1", "label": "Apple", "surface_texts": ["apple"]}]
                if text == "apple"
                else []
            ),
        ),
    )

    result = entity.get_surface_texts(bundle, "apple mango", word_correction=False)

    assert len(result["universal_entities"]) == 1
    assert result["universal_entities"][0]["entities"] == [
        {"entity_id": "Q1", "label": "Apple", "surface_text": "apple"},
    ]


def test_iter_no_tag_windows_builds_multi_word_windows():
    message_text = "satyam gpta is here"
    no_tags = [
        {"index": [0, 5]},
        {"index": [7, 10]},
        {"index": [12, 13]},
        {"index": [15, 18]},
    ]

    windows = list(entity._iter_no_tag_windows(message_text, no_tags))

    assert (0, 5, "satyam") in windows
    assert (7, 10, "gpta") in windows
    assert (0, 10, "satyam gpta") in windows


def test_iter_no_tag_windows_stops_at_non_whitespace_gap():
    message_text = "satyam.gpta"
    no_tags = [
        {"index": [0, 5]},
        {"index": [7, 10]},
    ]

    windows = list(entity._iter_no_tag_windows(message_text, no_tags))

    assert (0, 10, "satyam.gpta") not in windows
    assert (0, 5, "satyam") in windows
    assert (7, 10, "gpta") in windows


def test_find_fuzzy_matches():
    bundle = make_bundle(
        phrase_matcher=SimpleNamespace(
            get_suggestions=lambda text, max_edit_distance=None: (
                [("mayank", (3, 1))] if text == "myank" else []
            )
        ),
        entity_model=SimpleNamespace(
            get_entities_by_surface_text=lambda text: (
                [{"id": "Q1", "label": "Mayank", "surface_texts": ["mayank"]}]
                if text == "mayank"
                else []
            ),
        ),
    )

    message_text = "myank is here"
    no_tags = [
        {"index": [0, 4]},
        {"index": [6, 7]},
        {"index": [9, 12]},
    ]

    matches = list(entity._find_fuzzy_matches(bundle, message_text, no_tags))

    assert matches == [
        {
            "index": [0, 4],
            "surface_text": "myank",
            "corrected_text": "mayank",
            "score": -1,
            "entities": [
                {"entity_id": "Q1", "label": "Mayank", "surface_text": "mayank"}
            ],
        }
    ]


def test_get_surface_texts_word_correction_flag_gates_fuzzy_matches():
    bundle = make_bundle(
        phrase_matcher=SimpleNamespace(
            get_suggestions=lambda text, max_edit_distance=None: (
                [("mayank", (3, 1))]
                if text == "myank" and (max_edit_distance or 0) >= 1
                else []
            )
        ),
        entity_model=SimpleNamespace(
            get_entities_by_surface_text=lambda text: (
                [{"id": "Q1", "label": "Mayank", "surface_texts": ["mayank"]}]
                if text == "mayank"
                else []
            ),
        ),
    )

    result_off = entity.get_surface_texts(
        bundle, "myank is here", word_correction=False
    )
    assert result_off["universal_entities"] == []

    result_on = entity.get_surface_texts(bundle, "myank is here", word_correction=True)
    assert len(result_on["universal_entities"]) == 1
    assert result_on["universal_entities"][0]["corrected_text"] == "mayank"
    assert result_on["universal_entities"][0]["entities"] == [
        {"entity_id": "Q1", "label": "Mayank", "surface_text": "mayank"}
    ]

    no_tag_texts = [tag["surface_text"] for tag in result_on["no_tag_entities"]]
    assert "myank" not in no_tag_texts
    assert no_tag_texts == ["is", "here"]


def test_window_edit_distance_is_zero_when_correction_is_off():
    assert entity._window_edit_distance("bangalore", word_correction=False) == 0
    assert entity._window_edit_distance("go", word_correction=False) == 0


def test_window_edit_distance_caps_short_windows_at_one_edit():
    assert entity._window_edit_distance("go", word_correction=True) == 1
    assert entity._window_edit_distance("card", word_correction=True) == 1


def test_window_edit_distance_grants_two_edits_to_long_windows():
    assert entity._window_edit_distance("bangalore", word_correction=True) == 2
    assert entity._window_edit_distance("credit card", word_correction=True) == 2
    assert entity._window_edit_distance("abcde", word_correction=True) == 2  # exactly the threshold


def test_find_fuzzy_matches_allows_two_edits_on_a_long_window():
    # "benglore" is 2 edits from "bangalore" ('a'->'e', missing 'a').
    bundle = make_bundle(
        phrase_matcher=SimpleNamespace(
            get_suggestions=lambda text, max_edit_distance=None: (
                [("bangalore", (2, 2))]
                if text == "benglore" and (max_edit_distance or 0) >= 2
                else []
            )
        ),
        entity_model=SimpleNamespace(
            get_entities_by_surface_text=lambda text: (
                [{"id": "BLR", "label": "Bangalore", "surface_texts": ["bangalore"]}]
                if text == "bangalore"
                else []
            ),
        ),
    )

    no_tags = [{"index": [0, 7]}]
    matches = list(
        entity._find_fuzzy_matches(
            bundle, "benglore", no_tags, word_correction=True
        )
    )

    assert matches == [
        {
            "index": [0, 7],
            "surface_text": "benglore",
            "corrected_text": "bangalore",
            "score": -2,
            "entities": [
                {"entity_id": "BLR", "label": "Bangalore", "surface_text": "bangalore"}
            ],
        }
    ]


def test_find_fuzzy_matches_does_not_grant_two_edits_to_a_short_window():
    # Regression guard: a 2-edit budget on a 2-character window would let
    # "to" match unrelated short words like "goa".
    bundle = make_bundle(
        phrase_matcher=SimpleNamespace(
            get_suggestions=lambda text, max_edit_distance=None: (
                [("goa", (2, 2))]
                if text == "to" and (max_edit_distance or 0) >= 2
                else []
            )
        ),
        entity_model=SimpleNamespace(
            get_entities_by_surface_text=lambda text: (
                [{"id": "GOA", "label": "Goa", "surface_texts": ["goa"]}]
                if text == "goa"
                else []
            ),
        ),
    )

    no_tags = [{"index": [0, 1]}]
    matches = list(
        entity._find_fuzzy_matches(bundle, "to", no_tags, word_correction=True)
    )

    assert matches == []


def test_get_surface_texts_finds_exact_three_word_entity_with_correction_off():
    # The lemmatized phrase-cache loop only builds single-word and
    # adjacent-pair keys, so a 3-word entity can only be found through the
    # always-on distance-0 sweep. make_bundle()'s default lemmatizer stub
    # returns no lemmatized chunks, isolating that sweep as the only path
    # that could produce a match here.
    bundle = make_bundle(
        phrase_matcher=SimpleNamespace(
            get_suggestions=lambda text, max_edit_distance=None: (
                [("customer support team", (0, 0))]
                if text == "customer support team" and (max_edit_distance or 0) == 0
                else []
            )
        ),
        entity_model=SimpleNamespace(
            get_entities_by_surface_text=lambda text: (
                [{"id": "SUP", "label": "Customer Support", "surface_texts": ["customer support team"]}]
                if text == "customer support team"
                else []
            ),
        ),
    )

    result = entity.get_surface_texts(
        bundle, "customer support team", word_correction=False
    )

    assert len(result["universal_entities"]) == 1
    match = result["universal_entities"][0]
    assert match["corrected_text"] == "customer support team"
    assert match["score"] == 0
    assert match["entities"] == [
        {"entity_id": "SUP", "label": "Customer Support", "surface_text": "customer support team"}
    ]


def test_get_surface_texts_does_not_correct_typos_with_correction_off():
    # Regression guard: the always-on sweep must stay at distance 0 when
    # word_correction is False, so a typo must not slip through.
    bundle = make_bundle(
        phrase_matcher=SimpleNamespace(
            get_suggestions=lambda text, max_edit_distance=None: (
                [("bangalore", (1, 1))]
                if text == "banglore" and (max_edit_distance or 0) >= 1
                else []
            )
        ),
        entity_model=SimpleNamespace(
            get_entities_by_surface_text=lambda text: (
                [{"id": "BLR", "label": "Bangalore", "surface_texts": ["bangalore"]}]
                if text == "bangalore"
                else []
            ),
        ),
    )

    result = entity.get_surface_texts(bundle, "banglore", word_correction=False)

    assert result["universal_entities"] == []


def test_word_correction_end_to_end_with_real_matcher():
    """
    Same behavior as the tests above, but with no stubs at all: a real
    SymSpell-backed PhraseMatcher, a real SQLite-backed EntityModel, built
    the same way NamespaceRegistry builds one for a live namespace (see
    talkingdb_nel.services.namespace.registry._build_bundle).

    The stubbed tests above tell us `entity.py`'s own logic is correct for
    the inputs we hand-crafted. This test tells us that logic still holds
    once it is wired to the real edit-distance library - which matters
    because real Damerau-Levenshtein distance is not always what it looks
    like at a glance: a transposed pair of adjacent letters ("credit" ->
    "cerdit") is only 1 edit, not 2, and a stub can easily be written to
    disagree with that without anyone noticing.
    """

    from talkingdb_nel.services.namespace import registry as registry_module

    bundle = registry_module._build_bundle(f"wc-test-{uuid.uuid4()}")

    seeded = entity.bulk_create_entities(
        bundle,
        "csv",
        "entity_id,label,surface_texts\n"
        "BLR,Bangalore,bangalore\n"
        "CC,Credit Card,credit card\n"
        "SUP,Customer Support,customer support team\n",
    )
    assert seeded == {"created": 3, "errors": []}

    def ids_for(text, word_correction):
        result = entity.get_surface_texts(bundle, text, word_correction=word_correction)
        return {
            e["entity_id"]
            for u in result["universal_entities"]
            for e in u["entities"]
        }

    # Regression guard: worked before this fix, must keep working.
    assert ids_for("flight to bangalore", True) == {"BLR"}
    assert ids_for("credit card payment", True) == {"CC"}
    assert ids_for("banglore office", True) == {"BLR"}  # 1-edit
    assert ids_for("bangalore office", False) == {"BLR"}  # exact, correction off
    assert ids_for("go to the office", True) == set()  # no false positive
    assert ids_for("this is a test", True) == set()  # no false positive

    # Only pass with the fix: needs the real 2-edit budget on long windows.
    assert ids_for("benglore city", True) == {"BLR"}
    assert ids_for("bnglore weather", True) == {"BLR"}

    # Only pass with the fix: 3-word entity, correction off (phrase cache
    # only builds single-word/pair keys - this can only be found by the
    # always-on distance-0 sweep).
    assert ids_for("customer support team", False) == {"SUP"}


def test_create_regex_success():
    called = []

    bundle = make_bundle(
        entity_model=SimpleNamespace(has_entity=lambda entity_id: True),
        regex_model=SimpleNamespace(
            add_rule=lambda entity_id, regex: called.append((entity_id, regex)),
            save=lambda conn: None,
        ),
    )

    result = entity.create_regex(bundle, "Date", r"\d{4}")

    assert result == {"entity_id": "Date", "regex": r"\d{4}"}
    assert called == [("Date", r"\d{4}")]


def test_create_regex_missing_entity():
    bundle = make_bundle(
        entity_model=SimpleNamespace(has_entity=lambda entity_id: False)
    )

    with pytest.raises(entity.EntityNotFoundError):
        entity.create_regex(bundle, "Date", r"\d{4}")


def test_update_entity_label_only():
    updated = {}

    bundle = make_bundle(
        entity_model=SimpleNamespace(
            has_entity=lambda entity_id: True,
            update_label=lambda entity_id, label: updated.update(
                {"id": entity_id, "label": label}
            ),
            get_entity=lambda entity_id: {
                "id": entity_id,
                "label": updated.get("label", "Old Label"),
                "surface_texts": ["apple"],
            },
        )
    )

    result = entity.update_entity(bundle, "Q1", label="New Label")

    assert updated == {"id": "Q1", "label": "New Label"}
    assert result == {
        "entity_id": "Q1",
        "label": "New Label",
        "surface_texts": ["apple"],
    }


def test_update_entity_missing():
    bundle = make_bundle(
        entity_model=SimpleNamespace(has_entity=lambda entity_id: False)
    )

    with pytest.raises(entity.EntityNotFoundError):
        entity.update_entity(bundle, "Q1", label="X")


def test_update_entity_surface_texts_triggers_reindex():
    cleared = []
    word_loaded = []

    bundle = make_bundle(
        entity_model=SimpleNamespace(
            has_entity=lambda entity_id: True,
            update_surface_texts=lambda *args, **kwargs: None,
            get_entity=lambda entity_id: {
                "id": entity_id,
                "label": "Apple",
                "surface_texts": ["apple", "apple inc"],
            },
            iter_entities=lambda: iter(
                [
                    {
                        "id": "Q1",
                        "label": "Apple",
                        "surface_texts": ["apple", "apple inc"],
                    }
                ]
            ),
        ),
        dictionary=SimpleNamespace(clear=lambda: cleared.append(True)),
        word_matcher=SimpleNamespace(
            load=lambda docs: word_loaded.extend(docs),
            longest_word_length=5,
        ),
    )

    entity.update_entity(bundle, "Q1", surface_texts=["apple", "apple inc"])

    assert cleared == [True]
    assert word_loaded == [{"entity_id": "Q1", "surface_texts": ["apple", "apple inc"]}]


def test_delete_entity_success_triggers_reindex():
    removed = []
    cleared = []
    word_loaded = []

    bundle = make_bundle(
        entity_model=SimpleNamespace(
            has_entity=lambda entity_id: True,
            remove_entity=lambda entity_id: removed.append(entity_id),
            iter_entities=lambda: iter(
                [{"id": "Q2", "label": "Remaining", "surface_texts": ["remaining"]}]
            ),
        ),
        dictionary=SimpleNamespace(clear=lambda: cleared.append(True)),
        word_matcher=SimpleNamespace(
            load=lambda docs: word_loaded.extend(docs),
            longest_word_length=5,
        ),
    )

    entity.delete_entity(bundle, "Q1")

    assert removed == ["Q1"]
    assert cleared == [True]
    assert word_loaded == [{"entity_id": "Q2", "surface_texts": ["remaining"]}]


def test_delete_entity_missing():
    bundle = make_bundle(
        entity_model=SimpleNamespace(has_entity=lambda entity_id: False)
    )

    with pytest.raises(entity.EntityNotFoundError):
        entity.delete_entity(bundle, "Q1")


def test_update_fact_predicate_only():
    removed = []
    added = {}

    bundle = make_bundle(
        entity_model=SimpleNamespace(
            get_fact=lambda fact_id: {
                "id": fact_id,
                "source": "A",
                "target": "B",
                "predicate": "KNOWS",
                "since": 2020,
            },
            remove_fact=lambda fact_id: removed.append(fact_id),
            add_fact=lambda **kwargs: added.update(kwargs) or kwargs.get("fact_id"),
        )
    )

    result = entity.update_fact(bundle, "fact-1", predicate="WORKS_WITH")

    assert removed == ["fact-1"]
    assert added == {
        "source": "A",
        "target": "B",
        "predicate": "WORKS_WITH",
        "fact_id": "fact-1",
        "since": 2020,
    }
    assert result == {
        "id": "fact-1",
        "source": "A",
        "target": "B",
        "predicate": "WORKS_WITH",
        "since": 2020,
    }


def test_update_fact_missing():
    bundle = make_bundle(entity_model=SimpleNamespace(get_fact=lambda fact_id: None))

    with pytest.raises(entity.FactNotFoundError):
        entity.update_fact(bundle, "fact-1", predicate="X")


def test_delete_fact_success():
    removed = []

    bundle = make_bundle(
        entity_model=SimpleNamespace(
            get_fact=lambda fact_id: {
                "id": fact_id,
                "source": "A",
                "target": "B",
                "predicate": "KNOWS",
            },
            remove_fact=lambda fact_id: removed.append(fact_id),
        )
    )

    entity.delete_fact(bundle, "fact-1")

    assert removed == ["fact-1"]


def test_delete_fact_missing():
    bundle = make_bundle(entity_model=SimpleNamespace(get_fact=lambda fact_id: None))

    with pytest.raises(entity.FactNotFoundError):
        entity.delete_fact(bundle, "fact-1")


def test_list_regex_rules():
    bundle = make_bundle(
        entity_model=SimpleNamespace(has_entity=lambda entity_id: True),
        regex_model=SimpleNamespace(
            rules={
                "Date": [
                    SimpleNamespace(pattern=r"\d{4}"),
                    SimpleNamespace(pattern=r"\d{2}/\d{2}"),
                ]
            }
        ),
    )

    assert entity.list_regex_rules(bundle, "Date") == [r"\d{4}", r"\d{2}/\d{2}"]


def test_list_regex_rules_missing_entity():
    bundle = make_bundle(
        entity_model=SimpleNamespace(has_entity=lambda entity_id: False)
    )

    with pytest.raises(entity.EntityNotFoundError):
        entity.list_regex_rules(bundle, "Date")


def test_list_regex_rules_entity_with_no_rules():
    bundle = make_bundle(
        entity_model=SimpleNamespace(has_entity=lambda entity_id: True),
        regex_model=SimpleNamespace(rules={}),
    )

    assert entity.list_regex_rules(bundle, "Date") == []


def test_update_regex_rule_success():
    removed = []
    added = []

    bundle = make_bundle(
        regex_model=SimpleNamespace(
            remove_pattern=lambda rule_name, pattern: removed.append(
                (rule_name, pattern)
            ),
            add_rule=lambda rule_name, pattern: added.append((rule_name, pattern)),
        )
    )

    result = entity.update_regex_rule(bundle, "Date", r"\d{4}", r"\d{2}")

    assert removed == [("Date", r"\d{4}")]
    assert added == [("Date", r"\d{2}")]
    assert result == {"entity_id": "Date", "regex": r"\d{2}"}


def test_update_regex_rule_missing_pattern():
    def raise_key_error(rule_name, pattern):
        raise KeyError(rule_name)

    bundle = make_bundle(regex_model=SimpleNamespace(remove_pattern=raise_key_error))

    with pytest.raises(entity.RegexRuleNotFoundError):
        entity.update_regex_rule(bundle, "Date", "old", "new")


def test_delete_regex_rule_success():
    removed = []

    bundle = make_bundle(
        regex_model=SimpleNamespace(
            remove_pattern=lambda rule_name, pattern: removed.append(
                (rule_name, pattern)
            )
        )
    )

    entity.delete_regex_rule(bundle, "Date", r"\d{4}")

    assert removed == [("Date", r"\d{4}")]


def test_delete_regex_rule_missing():
    def raise_value_error(rule_name, pattern):
        raise ValueError(pattern)

    bundle = make_bundle(regex_model=SimpleNamespace(remove_pattern=raise_value_error))

    with pytest.raises(entity.RegexRuleNotFoundError):
        entity.delete_regex_rule(bundle, "Date", "nonexistent")
