from service import checkout


def test_checkout():
    assert checkout([1, 2]) == 3
