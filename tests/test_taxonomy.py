from casual_scout.analysis.taxonomy import (
    classify_app,
    classify_mechanic,
    classify_subgenre,
)


def test_classify_subgenre():
    genres = ['Games', 'Casual', 'Puzzle']
    assert classify_subgenre(genres) == 'Puzzle'

    genres = ['Games', 'Simulation', 'Casual']
    assert classify_subgenre(genres) == 'Simulation'

    genres = ['Games', 'Casual']
    assert classify_subgenre(genres) == 'Casual'

    assert classify_subgenre([]) == 'Casual'


def test_classify_mechanic_match_3():
    title = 'Royal Match'
    desc = 'Swap and match 3 tiles to build the royal castle.'
    result = classify_mechanic(title, desc)
    assert result['mechanic'] == 'Match-3'
    assert result['confidence'] in ('high', 'medium')
    assert 'match 3' in result['evidence'].lower() or 'match' in result['evidence'].lower()


def test_classify_mechanic_merge():
    title = 'Merge Mansion'
    desc = 'Discover secrets by merging items together to renovate the garden.'
    result = classify_mechanic(title, desc)
    assert result['mechanic'] == 'Merge'
    assert result['confidence'] in ('high', 'medium')
    assert 'merge' in result['evidence'].lower()


def test_classify_mechanic_sort():
    title = 'Water Sort Puzzle'
    desc = 'Sort colored water into glasses until all colors are together.'
    result = classify_mechanic(title, desc)
    assert result['mechanic'] == 'Sort'
    assert 'sort' in result['evidence'].lower()


def test_classify_mechanic_idle():
    title = 'Idle Hotel Tycoon'
    desc = 'Build your empire in this afk incremental management simulator.'
    result = classify_mechanic(title, desc)
    assert result['mechanic'] == 'Idle'
    assert 'idle' in result['evidence'].lower() or 'tycoon' in result['evidence'].lower()


def test_classify_mechanic_runner():
    title = 'Subway Surfers'
    desc = 'Dash and dodge trains in this endless runner adventure.'
    result = classify_mechanic(title, desc)
    assert result['mechanic'] == 'Runner'
    assert 'runner' in result['evidence'].lower() or 'dash' in result['evidence'].lower()


def test_classify_mechanic_card_board():
    title = 'Solitaire Grand Harvest'
    desc = 'Play classic solitaire tripeaks card game on your farm.'
    result = classify_mechanic(title, desc)
    assert result['mechanic'] == 'Card / Board'
    assert 'solitaire' in result['evidence'].lower() or 'card' in result['evidence'].lower()


def test_classify_mechanic_word_trivia():
    title = 'Wordscapes'
    desc = 'Connect letters to solve challenging crossword anagrams.'
    result = classify_mechanic(title, desc)
    assert result['mechanic'] == 'Word / Trivia'
    assert 'word' in result['evidence'].lower() or 'crossword' in result['evidence'].lower()


def test_classify_mechanic_drawing():
    title = 'Happy Color'
    desc = 'Relax with color by number and painting puzzles for adults.'
    result = classify_mechanic(title, desc)
    assert result['mechanic'] == 'Drawing'
    assert 'color by number' in result['evidence'].lower() or 'paint' in result['evidence'].lower()


def test_classify_mechanic_unknown():
    title = 'Generic App'
    desc = 'A nice application for everyone.'
    result = classify_mechanic(title, desc)
    assert result['mechanic'] == 'Other'
    assert result['confidence'] == 'unknown'
    assert result['evidence'] is None


def test_classify_app_full():
    genres = ['Games', 'Casual', 'Puzzle']
    title = 'Tile Club - Match 3 Puzzle'
    desc = 'Triple match 3d tiles in this classic matching brain game.'
    classified = classify_app(genres, title, desc)
    assert classified['subgenre'] == 'Puzzle'
    assert classified['mechanic'] == 'Match-3'
    assert classified['confidence'] == 'high'
    assert classified['evidence'] is not None
