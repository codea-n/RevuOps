# bad_code_example.py
# Intentionally flawed code to test AutoReviewer agents

import os
import sys  # unused import — Ruff will flag this

# Hardcoded secret — Bandit will flag this
PASSWORD = "supersecret123"
API_KEY = "sk-1234567890abcdef"

def get_user(user_id):
    # SQL injection risk — Bandit will flag this
    query = "SELECT * FROM users WHERE id = " + str(user_id)
    return query

def slow_function(data):
    # O(n^2) nested loop — performance agent will flag this
    results = []
    for i in data:
        for j in data:
            if i == j:
                results.append(i)
    return results

def read_file(path):
    # No exception handling on file open
    f = open(path)
    return f.read()
    # file never closed — resource leak