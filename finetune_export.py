# finetune_export.py
# Run manually when you have enough feedback:
#   python finetune_export.py
#
# Produces: training_data.jsonl — ready for fine-tuning

import json
import os
from dotenv import load_dotenv
load_dotenv()

from app.db.repository import get_reviews_with_feedback

# How many feedback records before we bother exporting
MIN_FEEDBACK_THRESHOLD = 50

# Only export reviews where feedback was positive
# "partial" = some findings were good, include with lower weight
POSITIVE_SIGNALS = {"accepted", "partial"}


def build_training_example(record: dict) -> dict | None:
    """
    Converts one feedback record into an OpenAI-compatible
    fine-tuning example (works with Groq fine-tuning too).

    Format: {"messages": [system, user, assistant]}
    - system: the reviewer role
    - user: the security findings that were analysed
    - assistant: the review text the developer accepted
    """
    signal = record.get("signal")
    if signal not in POSITIVE_SIGNALS:
        return None  # skip rejected reviews — don't train on bad examples

    review = record.get("reviews", {})
    if not review:
        return None

    security = review.get("security_findings", {})
    review_text = review.get("review_text", "")
    repo = review.get("repo", "unknown")

    if not review_text:
        return None

    # Build the user message — what the model saw as input
    user_content = (
        f"Repository: {repo}\n\n"
        f"Security findings: {json.dumps(security, indent=2)}\n\n"
        f"Please review this code change."
    )

    return {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert code reviewer. "
                    "Write concise, actionable GitHub PR review comments."
                )
            },
            {
                "role": "user",
                "content": user_content
            },
            {
                "role": "assistant",
                "content": review_text
            }
        ]
    }


def main():
    print("Fetching feedback from Supabase...")
    records = get_reviews_with_feedback(limit=1000)

    print(f"Found {len(records)} feedback records")

    if len(records) < MIN_FEEDBACK_THRESHOLD:
        print(
            f"Not enough feedback yet — need {MIN_FEEDBACK_THRESHOLD}, "
            f"have {len(records)}. Keep collecting."
        )
        return

    examples = []
    skipped = 0

    for record in records:
        example = build_training_example(record)
        if example:
            examples.append(example)
        else:
            skipped += 1

    print(f"Built {len(examples)} training examples ({skipped} skipped/rejected)")

    if not examples:
        print("No valid examples to export.")
        return

    # Write JSONL — one JSON object per line, no wrapping array.
    # This is the format every major LLM fine-tuning API expects.
    output_path = "training_data.jsonl"
    with open(output_path, "w") as f:
        for example in examples:
            f.write(json.dumps(example) + "\n")

    print(f"Exported to {output_path}")
    print(f"Next step: upload {output_path} to your fine-tuning provider")


if __name__ == "__main__":
    main()