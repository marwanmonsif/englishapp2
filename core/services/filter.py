import re

BAD_WORDS = [
    'damn', 'hell', 'crap', 'idiot', 'stupid', 'dumb', 'loser',
    'hate', 'ugly', 'shut up', 'shutup', 'moron', 'jerk',
]

def filter_message(text):
    """Returns (filtered_text, violation_count)"""
    violations = 0
    result = text
    for word in BAD_WORDS:
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        count = len(pattern.findall(result))
        if count > 0:
            violations += count
            replacement = '*' * len(word)
            result = pattern.sub(replacement, result)
    return result, violations
