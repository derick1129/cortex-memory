from cortex.engine.token_budgeter import TokenBudgeter


def test_token_budget_packing():
    budgeter = TokenBudgeter(max_tokens=100)
    items = [
        {"section": "Arch", "content": "Short text 1"},
        {"section": "Arch", "content": "Short text 2"},
        {"section": "Arch", "content": "A" * 2000},  # should be truncated/dropped
    ]
    packed = budgeter.pack(items)
    assert len(packed) < 500
    assert "Short text 1" in packed
    assert "Short text 2" in packed
    assert "A" * 2000 not in packed


def test_token_budget_empty_items():
    budgeter = TokenBudgeter(max_tokens=500)
    packed = budgeter.pack([])
    assert packed == ""


def test_token_budget_default_section():
    budgeter = TokenBudgeter(max_tokens=500)
    items = [{"content": "Important context without explicit section title"}]
    packed = budgeter.pack(items)
    assert "### Context" in packed
    assert "Important context without explicit section title" in packed


def test_token_budget_estimate_tokens():
    budgeter = TokenBudgeter(max_tokens=1000)
    assert budgeter.estimate_tokens("") == 1
    assert budgeter.estimate_tokens("abc") == 1
    assert budgeter.estimate_tokens("abcd") == 1
    assert budgeter.estimate_tokens("abcdefgh") == 2
    assert budgeter.estimate_tokens("a" * 400) == 100
