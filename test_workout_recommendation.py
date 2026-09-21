from workout_recommendation import evaluate_planned_workout


result = evaluate_planned_workout(
    sport="cycling",
    planned_duration_minutes=90,
    planned_intensity="THRESHOLD",
    planned_workout="90 minute bike with 4x10 minute threshold intervals"
)

print("=" * 70)
print("PLANNED WORKOUT EVALUATION")
print("=" * 70)

for key, value in result.items():
    print(f"{key}: {value}")