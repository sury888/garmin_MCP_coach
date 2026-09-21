from recommendations import get_workout_recommendation


print("=" * 70)
print("WORKOUT RECOMMENDATION TEST")
print("=" * 70)

result = get_workout_recommendation()

print("\nDATE:")
print(result["date"])

print("\nRECOMMENDATION:")
print(result["recommendation"])

print("\nRECOVERY:")
print(
    f'{result["recovery_score"]}/100 '
    f'({result["recovery_status"]})'
)

print("\nINTENSITY:")
print(result["intensity"])

print("\nDURATION:")
print(result["duration"])

print("\nALLOWED SPORTS:")
for sport in result["allowed_sports"]:
    print(f"• {sport}")

print("\nAVOID:")
for item in result["avoid"]:
    print(f"• {item}")

print("\nREASONING:")
for reason in result["reasoning"]:
    print(f"• {reason}")