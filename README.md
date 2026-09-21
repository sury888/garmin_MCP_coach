GARMIN COACH — INTERVAL-FIRST COACHING CONTEXT PATCH

This patch changes the coaching context so Claude receives Garmin-native lap/interval data before reasoning about today's training.

FILES
- analytics.py — adds today_workouts to generate_coaching_context and removes Training Readiness from coaching context/flags.
- coaching_workouts.py — fetches today's endurance-session Garmin-native laps, performs per-lap analysis and data-quality checks, and attaches available historical performance records.
- health_trends.py — removes Training Readiness from health trend calculations/signals.
- coach.py — removes Training Readiness from recovery scoring and coaching trend signals.
- daily_report.py — adds today's native workout analysis to the daily report.
- server.py — adds get_today_workout_intervals tool.
- intervals_analysis.py — included so the patch remains aligned with the current lap metric helpers.

INSTALL
Replace the matching files in your garminCustomMcp project.

TEST AFTER RESTARTING CLAUDE DESKTOP
1. Run get_today_workout_intervals.
2. Verify today's endurance sessions contain Garmin-native laps.
3. Verify Training Readiness does not appear in that output.
4. Run get_coaching_context and verify it contains today_workouts.
5. Ask Claude for a coaching analysis. It should prioritize interval/lap execution, historical comparison, training load, then recovery context.

DATA POLICY
- Garmin-native lap boundaries only.
- No invented work/recovery boundaries.
- Invalid Garmin values are flagged instead of interpreted.
- Bike sessions with one continuous Garmin lap remain one continuous lap.
- Training Readiness is intentionally excluded from the coaching pipeline.
