"""Who the student is, as far as stage 1 (intake) could find out.

The profile exists because "what counts as already known" is the single most
important input to teaching, and it used to be a hard-coded assumption. A
student who says they are a beginner needs everything explained; one who is
intermediate already has the field's basics and needs only what is new to
them explained in depth. The level therefore changes what the teacher treats
as known — it never changes the rule that new material is explained fully
before it is used.

Validation lives here, once. The routes, the plan generator, the syllabus
generator and the teacher's prompts all read a LearnerProfile rather than
each parsing a loose dict and each deciding for themselves what a missing or
odd value means.
"""

from dataclasses import dataclass

LEVELS = ("beginner", "intermediate", "expert")
DEPTHS = ("basics", "practical", "expert")
LEVEL_SOURCES = ("stated", "diagnosed")

MIN_TIME_MINUTES = 5
MAX_TIME_MINUTES = 600

LEVEL_LABELS = {"beginner": "מתחיל", "intermediate": "בינוני", "expert": "מתקדם"}
DEPTH_LABELS = {"basics": "יסודות", "practical": "שימושי", "expert": "מעמיק-מקצועי"}


PRESUMED_KNOWN = {
    "beginner": (
        "הנח שהתלמיד לא מכיר את הנושא בכלל ואין לו שום רקע בו. אל תניח שום ידע קודם, "
        "גם לא ידע שנראה לך בסיסי ומובן מאליו."
    ),
    "intermediate": (
        "התלמיד מכיר את יסודות התחום, אבל לא את מה שנלמד בשיעור הזה. יסודות שהשיעור "
        "נשען עליהם — די בתזכורת קצרה. כל מה שחדש לו — הסבר בפירוט מלא, כאילו אינו מכיר "
        "אותו בכלל."
    ),
    "expert": (
        "התלמיד מכיר היטב את התחום. אל תסביר יסודות ואל תעמוד על מונחים מקובלים בתחום; "
        "התמקד במה שמעמיק, מדויק או מתקדם. אבל אם עולה דבר שייתכן שלא פגש — הסבר אותו."
    ),
}


class InvalidProfileError(ValueError):
    pass


@dataclass(frozen=True)
class LearnerProfile:
    topic: str
    time_budget_minutes: int
    target_depth: str
    starting_level: str
    goal: str = ""
    # "diagnosed" when the level came from the short quiz rather than the
    # student's own say-so — people mis-rate themselves in both directions,
    # so the teacher is told which it was.
    level_source: str = "stated"

    @classmethod
    def from_dict(cls, data: dict | None) -> "LearnerProfile":
        if not isinstance(data, dict):
            raise InvalidProfileError("profile must be an object")

        topic = str(data.get("topic") or "").strip()
        if not topic:
            raise InvalidProfileError("topic is required")

        minutes = data.get("time_budget_minutes")
        # bool is an int subclass; True would otherwise sneak through as 1.
        if isinstance(minutes, bool) or not isinstance(minutes, int):
            raise InvalidProfileError("time_budget_minutes must be a whole number of minutes")
        if not (MIN_TIME_MINUTES <= minutes <= MAX_TIME_MINUTES):
            raise InvalidProfileError(
                f"time_budget_minutes must be between {MIN_TIME_MINUTES} and {MAX_TIME_MINUTES}"
            )

        depth = data.get("target_depth")
        if depth not in DEPTHS:
            raise InvalidProfileError(f"target_depth must be one of {DEPTHS}")

        level = data.get("starting_level")
        if level not in LEVELS:
            raise InvalidProfileError(f"starting_level must be one of {LEVELS}")

        source = data.get("level_source") or "stated"
        if source not in LEVEL_SOURCES:
            raise InvalidProfileError(f"level_source must be one of {LEVEL_SOURCES}")

        return cls(
            topic=topic,
            time_budget_minutes=minutes,
            target_depth=depth,
            starting_level=level,
            goal=str(data.get("goal") or "").strip(),
            level_source=source,
        )

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "time_budget_minutes": self.time_budget_minutes,
            "target_depth": self.target_depth,
            "starting_level": self.starting_level,
            "goal": self.goal,
            "level_source": self.level_source,
        }

    def describe(self) -> str:
        """The profile as a block of Hebrew for a prompt."""
        source = "נקבעה לפי בוחן אבחון קצר" if self.level_source == "diagnosed" else "לפי דיווח התלמיד"
        lines = [
            f"רמת פתיחה: {LEVEL_LABELS[self.starting_level]} ({source})",
            f"עומק מבוקש: {DEPTH_LABELS[self.target_depth]}",
            f"זמן פנוי: {self.time_budget_minutes} דקות",
        ]
        if self.goal:
            lines.append(f"מטרת התלמיד: {self.goal}")
        return "\n".join(lines)

    def presumed_known(self) -> str:
        """What the teacher may treat as already known, by level. This table
        is the ONLY place that decision is made."""
        return PRESUMED_KNOWN[self.starting_level]

    def depth_guidance(self) -> str:
        return {
            "basics": "העומק המבוקש: יסודות. תן הבנה מוצקה של הרעיון המרכזי, בלי להיכנס למקרי קצה.",
            "practical": "העומק המבוקש: שימושי. הדגש מה עושים עם זה בפועל, ודוגמאות מהעולם האמיתי.",
            "expert": "העומק המבוקש: מעמיק-מקצועי. כלול דיוק, מקרי קצה והנימוקים שמאחורי הכללים.",
        }[self.target_depth]
