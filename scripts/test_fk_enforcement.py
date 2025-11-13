"""Test that foreign key constraints are enforced"""

from database.db import UnifiedDatabase

db = UnifiedDatabase("/root/engagic/data/engagic.db")

# Get a real meeting_id
count = db.conn.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
print(f"Total meetings: {count}")

result = db.conn.execute("SELECT id FROM meetings LIMIT 1").fetchone()
print(f"Query result: {result}")
print(f"Result keys: {result.keys() if result else 'None'}")

if not result:
    print("SKIP: No meetings in database to test with")
    exit(0)

meeting_id = result['id']
print(f"Using meeting_id: {meeting_id}")

# Try to insert item with fake matter_id - should fail
try:
    db.conn.execute("""
        INSERT INTO items (id, meeting_id, title, sequence, matter_id)
        VALUES (?, ?, 'Test Item', 999, 'fake_matter_id_that_does_not_exist')
    """, ('test_fk_enforcement', meeting_id))
    db.conn.commit()
    print("FAIL: FK constraint not enforced (insert succeeded)")
except Exception as e:
    if "FOREIGN KEY constraint failed" in str(e):
        print("PASS: FK constraint correctly enforced")
        print(f"Error: {e}")
    else:
        print(f"UNEXPECTED ERROR: {e}")

# Cleanup
db.conn.execute("DELETE FROM items WHERE id = 'test_fk_enforcement'")
db.conn.commit()
