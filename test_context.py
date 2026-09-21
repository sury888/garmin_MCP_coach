from analytics import generate_coaching_context
import json

print("=" * 70)
print("COACHING CONTEXT TEST")
print("=" * 70)

context = generate_coaching_context()

print(json.dumps(context, indent=2, default=str))