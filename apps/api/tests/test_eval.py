from eval.run import match


def test_match_pairs_similar_descriptions_once():
    expected = [{"description": "Update the PriceLabs rule for The View"}, {"description": "Call the plumber"}]
    actual = [{"description": "Update PriceLabs min-stay rule for The View"}, {"description": "Order more towels"}]
    pairs = match(expected, actual)
    assert pairs[0][1] is actual[0] and pairs[1][1] is None
