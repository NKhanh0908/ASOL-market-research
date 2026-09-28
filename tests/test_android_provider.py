from casual_scout.android import provider


def test_extract_store_category_and_genre_from_google_play_metadata():
    extract_store_classification = getattr(provider, "extract_store_classification", None)
    assert callable(extract_store_classification)
    result = extract_store_classification(
        {"applicationCategory": "GAME_CASUAL"},
        [
            {
                "label": "Mô phỏng",
                "href": "https://play.google.com/store/apps/category/GAME_SIMULATION",
            }
        ],
    )

    assert result == {
        "application_category": "GAME_CASUAL",
        "google_play_genres": [{"label": "Mô phỏng", "code": "GAME_SIMULATION"}],
    }


def test_missing_google_play_category_stays_unknown():
    extract_store_classification = getattr(provider, "extract_store_classification", None)
    assert callable(extract_store_classification)
    result = extract_store_classification({}, [])

    assert result == {"application_category": None, "google_play_genres": []}
