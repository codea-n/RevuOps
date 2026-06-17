# test_db.py — run once, then delete
from dotenv import load_dotenv
load_dotenv()

from app.db.repository import save_review, save_feedback, get_reviews_with_feedback

# Save a fake review
review_id = save_review(
    pr_number=99,
    repo="test/repo",
    review_text="## Security\n- Line 3: MD5 hash detected",
    security_findings={"issues": [], "high_count": 1},
    performance_findings={"hotspots": []},
    architecture_findings={"notes": []},
)
print(f"Saved review: {review_id}")

# Save feedback for it
save_feedback(review_id, "accepted", "Good catch on the MD5")
print("Feedback saved")

# Read it back
records = get_reviews_with_feedback()
print(f"Found {len(records)} feedback records")
print(records[0])