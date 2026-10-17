"""Small, intentionally transparent indexing fixture. Never executed by indexing."""

def normalize(value):
    """Normalize a numeric value."""
    return max(0, value)


def total(values):
    """Sum normalized values."""
    return sum(normalize(value) for value in values)


class Calculator:
    def calculate(self, values):
        return total(values)
