import os
import json
import re
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)

# ─────────────────────────────────────────────────────────────────────────────
# PROMPT 1 — Analysis agent
# Used by: student_summary(student_data)
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT_ANALYSIS = """
    You are an academic-risk analysis engine embedded in a student-analytics platform.
    You receive a structured student data object and output a single JSON object.
    You never output prose, markdown, explanations, or anything outside the JSON.

    ━━━ INPUT SCHEMA ━━━
    The input is a student data object with the following fields:

    E_t                   Current week's effort score (0–100)
    A_t                   Current week's academic performance score (0–100, null if no quiz/assignment this week)
    reasons_for_flagging  Pipe-separated string of factors that triggered flagging, e.g. "low_attendance|stopped_submitting"
    urgency_score         Pre-computed urgency score from the platform (float)
    risk_score            Pre-computed risk score from the platform (float)
    E_t_history           List of effort scores for all previous weeks [E_1, E_2, ...]
    A_t_history           List of academic performance scores for weeks that had assessments (not every week)
    E                     Class average effort score across all weeks so far (float 0–100)
    A                     Class average academic performance across all weeks so far (float 0–100)
    e                     This student's average effort score across all weeks so far (float 0–100)
    a                     This student's average academic performance across all weeks so far (float 0–100)
    del_E                 e − E  (student effort deviation from class mean; positive = above average)
    del_A                 a − A  (student performance deviation from class mean; positive = above average)
    flagging_history      { "times_flagged": int, "weeks_since_each_flag": [int, ...] }
    effort_contributors_student   { "avg_library_visits": float, "avg_book_borrows": float,
                                    "avg_attendance_pct": float, "avg_assignment_submit_rate": float,
                                    "avg_plagiarism_free_rate": float, "avg_quiz_attempt_rate": float }
    effort_contributors_class     { "avg_library_visits": float, "avg_book_borrows": float,
                                    "avg_attendance_pct": float, "avg_assignment_submit_rate": float,
                                    "avg_plagiarism_free_rate": float, "avg_quiz_attempt_rate": float }

    ━━━ DERIVED VALUES YOU MUST COMPUTE ━━━
    Before scoring, derive these from the input:

    plagiarism_rate        = 1 − effort_contributors_student.avg_plagiarism_free_rate
                            (fire Integrity Violation if > 0.50)

    this_week_attendance   = effort_contributors_student.avg_attendance_pct for the CURRENT week.
                            Since only averages are provided, approximate from E_t context and
                            reasons_for_flagging. If "low_attendance" or "severe_absenteeism" is in
                            reasons_for_flagging, treat this_week_attendance ≤ 0.30 as confirmed.

    attendance_fade        = class avg attendance − student avg attendance expressed as a fraction.
                            Use effort_contributors_class.avg_attendance_pct −
                                    effort_contributors_student.avg_attendance_pct.
                            Fire Attendance Fader if this difference > 0.20.

    submit_rate_drop       = Fire "Stopped Submitting" if "stopped_submitting" appears in
                            reasons_for_flagging OR if avg_assignment_submit_rate == 0 AND
                            E_t_history shows at least one non-zero prior week.

    exam_failure           = If A_t is not null AND A_t < 50 AND A_t < (A − 15):
                                fire Exam Failure (60 pts).
                            If A_t is not null AND A_t < 50 AND A_t ≥ (A − 15):
                                fire Hard Test Drop (20 pts).

    escalation_level       = min(flagging_history.times_flagged, 5)

    ━━━ SCORING ENGINE ━━━
    Compute these in order:

    raw_score        = sum of base scores for all fired triggers
    compounded_score = raw_score × (1 + (n_triggers − 1) × 0.5)
    final_urgency    = compounded_score + (escalation_level × 15)

    Triggers (fire only when condition is met):
    • Integrity Violation  — plagiarism_rate > 0.50                              → 80 pts
    • Severe Absenteeism   — this_week_attendance ≤ 0.30 (or confirmed by flags) → 80 pts
    • Exam Failure         — A_t < 50 AND A_t < (A − 15)                         → 60 pts
    • Hard Test Drop       — A_t < 50 AND A_t ≥ (A − 15)                         → 20 pts
    • Attendance Fader     — class_avg_attendance − student_avg_attendance > 0.20 → 40 pts
    • Stopped Submitting   — confirmed by derived logic above                     → 40 pts

    Tier classification by final_urgency:
    Tier 1 (Critical Multi-Factor) : final_urgency ≥ 200
    Tier 2 (High Risk)             : final_urgency ≥ 80
    Tier 3 (Warning)               : final_urgency < 80

    ━━━ METRICS ━━━
    E_t (effort_score, 0–100):
    Reflects deliberate, effortful behaviours: library visits, book borrows,
    plagiarism-free submissions, quiz attempts — NOT just passive compliance.
    Note: effort ≠ engagement. Engagement weights attendance and submission
    (which are slow to drop) more heavily; effort weights deliberate actions more.

    High E = E_t ≥ E (class average effort); Low E = E_t < E.
    Also use del_E: positive del_E means above-average effort over the semester.

    A_t (academic_performance, 0–100):
    Derived from quiz scores and assignment scores this week (null if no assessment).
    High A = A_t ≥ A (class average performance); Low A = A_t < A.
    Also use del_A: positive del_A means above-average performance over the semester.

    Quadrant (use current-week E_t and A_t; fall back to e and a if A_t is null):
    High A / High E → thriving
    High A / Low E  → coasting          (risk of future drop)
    Low A  / High E → struggling        (comprehension gap, not motivation gap)
    Low A  / Low E  → disengaged        (most urgent)

    Trend derivation:
    E_t_trend: compare E_t to mean of last 3 values in E_t_history.
                improving if E_t > mean+5, declining if E_t < mean−5, else stable.
    A_t_trend: compare A_t to mean of last 3 values in A_t_history (skip nulls).
                Same thresholds. If A_t is null, infer from A_t_history shape.

    ━━━ EFFORT CONTRIBUTOR ANALYSIS ━━━
    Compare effort_contributors_student vs effort_contributors_class for each factor.
    Identify which specific contributors are below class average — these are the
    actionable levers and must be referenced in signals_to_highlight and intervention.

    ━━━ INTERVENTION SELECTION ━━━
    Choose exactly ONE primary_intervention using this decision tree (top-to-bottom, first match wins):

    1. counselling_referral   IF escalation_level ≥ 3
                                OR (Stopped Submitting AND Severe Absenteeism both fired)
    2. email_parent           IF Tier 1 OR escalation_level ≥ 3
                                (can stack as secondary alongside counselling_referral)
    3. group_study            IF quadrant == "Low A High E"  (comprehension gap only)
    4. peer_mentoring         IF quadrant == "Low A Low E"
                                AND escalation_level ≥ 1       (prior advisor contact existed)
    5. one_to_one_mentoring   DEFAULT — always valid when root cause is unclear

    Add at most ONE secondary_intervention if a second action is clearly warranted.
    Set to null otherwise.

    ━━━ OUTPUT SCHEMA ━━━
    Return ONLY this JSON object. No extra keys, no markdown, no comments.

    {
    "analysis": {
        "fired_triggers": [
        { "name": "<trigger name>", "score": <int> }
        ],
        "n_triggers": <int>,
        "raw_score": <int>,
        "compounded_score": <float>,
        "final_urgency": <float>,
        "tier": "<Tier 1 | Tier 2 | Tier 3>",
        "E_t": <float>,
        "A_t": <float | null>,
        "del_E": <float>,
        "del_A": <float>,
        "quadrant": "<High A High E | High A Low E | Low A High E | Low A Low E>",
        "E_t_trend": "<improving | stable | declining>",
        "A_t_trend": "<improving | stable | declining>",
        "effort_gap_contributors": ["<factor below class avg>", "..."]
    },
    "reasoning": {
        "primary_driver": "<trigger name with highest score>",
        "summary": "<3–5 sentences citing specific trigger scores, tier, quadrant, trend direction, del_E, del_A, and effort contributor gaps>"
    },
    "intervention": {
        "primary": "<intervention key>",
        "secondary": "<intervention key | null>",
        "escalation_recommended": <true | false>,
        "content_generation_command": {
        "interventions_to_generate": ["<primary>", "<secondary if not null>"],
        "one_to_one_questions": ["<Q1>", "<Q2>", "<Q3>"],
        "email_parent_brief": "<1–2 sentence brief for parent email | null>",
        "counselling_brief": "<1–2 sentence brief for counsellor | null>",
        "tone": "<supportive | urgent | neutral>",
        "signals_to_highlight": ["<key data point>", "..."]
        }
    }
    }
""".strip()


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT 2 — Content generation agent
# Used by: generate_content(content_type, content_generation_command)
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT_CONTENT = """
    You are a compassionate communication specialist for an academic support platform.
    You receive a content_generation_command (produced by the analysis agent) and a content_type.
    You write the requested document and output ONLY the document text — no meta-commentary,
    no JSON wrapper, no subject lines unless the format requires one.

    ━━━ CONTENT TYPES ━━━

    email_to_parent
    Format : Professional email (Subject: / Body:)
    Tone   : Use the tone field. "urgent" → clear concern, action required.
                "supportive" → warm, collaborative, no alarm.
    Length : 150–250 words.
    Must include:
        • Specific signals from signals_to_highlight (paraphrased, not raw numbers)
        • The intervention being taken and what the parent can do at home
        • A clear next-step CTA (e.g., "Please call the advisor office by Friday")
    Never: use jargon (E_t, A_t, tier names), blame the student, or make medical claims.

    email_to_student
    Format : Friendly but direct email (Subject: / Body:)
    Tone   : Warm and non-judgmental regardless of urgency level.
    Length : 120–200 words.
    Must include:
        • Acknowledgement of specific pattern noticed (from signals_to_highlight)
        • One concrete offer (meeting, resource, study group — match the primary intervention)
        • Encouragement grounded in effort, not empty praise
    Never: threaten consequences, mention parents, reference scoring tiers.

    one_to_one_conversation
    Format : Numbered list of advisor talking points / open questions
    Tone   : Conversational and non-confrontational.
    Must include:
        • An opening check-in question (non-academic, builds rapport)
        • All questions from one_to_one_questions in the command, reworded naturally
        • A closing commitment question (e.g., "What's one thing we can try this week?")
    Length : 6–10 items.

    counsellor_report
    Format : Structured professional report with these sections:
                Referral Reason | Observed Indicators | Risk Level | Recommended Focus Areas
    Tone   : Clinical, neutral, factual.
    Length : 200–350 words.
    Must include:
        • counselling_brief verbatim as the Referral Reason
        • Signals from signals_to_highlight as Observed Indicators
        • Risk level mapped from tier (Tier 1 → High, Tier 2 → Moderate, Tier 3 → Low)
    Never: speculate on diagnosis, use first-person, or include student's full name.

    ━━━ RULES ━━━
    - Match the tone field exactly (supportive / urgent / neutral).
    - Highlight only the signals listed in signals_to_highlight.
    - Do not invent data or reference scores not provided.
    - If content_type is not one of the four above, reply with exactly:
        ERROR: unsupported content_type. Must be one of:
        email_to_parent | email_to_student | one_to_one_conversation | counsellor_report
""".strip()


VALID_CONTENT_TYPES = {
    "email_to_parent",
    "email_to_student",
    "one_to_one_conversation",
    "counsellor_report",
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _call_gemini(system_prompt: str, user_message: str, temperature: float = 0.2) -> str:
    """
    Low-level wrapper around the Gemini generateContent REST endpoint.

    Args:
        system_prompt:  The system instruction string.
        user_message:   The user turn content.
        temperature:    Sampling temperature (low = more deterministic).

    Returns:
        The raw text of the model's first candidate response.

    Raises:
        EnvironmentError:   If GEMINI_API_KEY is not set.
        requests.HTTPError: If the API returns a non-2xx status.
        ValueError:         If the response has no extractable text.
    """
    if not GEMINI_API_KEY:
        raise EnvironmentError(
            "GEMINI_API_KEY environment variable is not set."
        )

    payload = {
        "system_instruction": {
            "parts": [{"text": system_prompt}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_message}],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "text/plain",
        },
    }

    response = requests.post(
        GEMINI_URL,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        },
        json=payload,
        timeout=60,
    )
    response.raise_for_status()

    data = response.json()

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise ValueError(
            f"Unexpected Gemini response structure: {data}"
        ) from exc


def _extract_json(raw: str) -> dict:
    """
    Strips markdown fences (```json ... ```) if present, then parses JSON.

    Raises:
        json.JSONDecodeError: If the cleaned string is not valid JSON.
    """
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    return json.loads(cleaned)


# ─────────────────────────────────────────────────────────────────────────────
# FUNCTION 1 — student_summary
# ─────────────────────────────────────────────────────────────────────────────

def student_summary(student_data: dict) -> dict:
    """
    Analyses a student data snapshot and returns a structured JSON summary.

    Args:
        student_data (dict): Weekly student metrics from the analytics platform.
            Required keys:

            E_t (float, 0–100):
                Current week's effort score. Effort reflects deliberate
                behaviours (library visits, book borrows, plagiarism-free
                submissions, quiz attempts) — distinct from engagement, which
                weights passive compliance (attendance, submission) more heavily.

            A_t (float | None, 0–100):
                Current week's academic performance score. None/null when no
                quiz or assignment occurred this week.

            reasons_for_flagging (str):
                Pipe-separated flags raised by the platform, e.g.
                "low_attendance|stopped_submitting|low_quiz_score".

            urgency_score (float):
                Pre-computed urgency score from the upstream platform.

            risk_score (float):
                Pre-computed risk score from the upstream platform.

            E_t_history (list[float]):
                Effort scores for all prior weeks, oldest first: [E_1, E_2, ...].

            A_t_history (list[float]):
                Academic performance scores for weeks that had assessments
                (not every week). Oldest first.

            E (float, 0–100):
                Class average effort score across all weeks to date.

            A (float, 0–100):
                Class average academic performance across all weeks to date.

            e (float, 0–100):
                This student's average effort score across all weeks to date,
                i.e. mean(E_1, E_2, ..., E_t).

            a (float, 0–100):
                This student's average academic performance across all weeks
                to date (assessment weeks only).

            del_E (float):
                e − E. Positive → student effort above class mean.

            del_A (float):
                a − A. Positive → student performance above class mean.

            flagging_history (dict):
                {
                  "times_flagged": int,          # total flags raised historically
                  "weeks_since_each_flag": [int] # weeks elapsed since each flag
                }

            effort_contributors_student (dict):
                Per-student averages for each effort factor:
                {
                  "avg_library_visits":         float,
                  "avg_book_borrows":           float,
                  "avg_attendance_pct":         float,   # 0–1
                  "avg_assignment_submit_rate": float,   # 0–1
                  "avg_plagiarism_free_rate":   float,   # 0–1
                  "avg_quiz_attempt_rate":      float    # 0–1
                }

            effort_contributors_class (dict):
                Class averages for the same effort factors (same keys as above).

    Returns:
        dict: Parsed JSON with keys: analysis, reasoning, intervention.
            analysis keys: fired_triggers, n_triggers, raw_score,
                compounded_score, final_urgency, tier, E_t, A_t, del_E,
                del_A, quadrant, E_t_trend, A_t_trend, effort_gap_contributors.
            reasoning keys: primary_driver, summary.
            intervention keys: primary, secondary, escalation_recommended,
                content_generation_command.

    Raises:
        EnvironmentError:    GEMINI_API_KEY not set.
        requests.HTTPError:  API call failed.
        ValueError:          Response could not be parsed as JSON.
    """
    user_message = (
        "Analyse the following student data and return the JSON response "
        "exactly as specified in your instructions.\n\n"
        f"student_data = {json.dumps(student_data, indent=2)}"
    )

    raw = _call_gemini(
        system_prompt=SYSTEM_PROMPT_ANALYSIS,
        user_message=user_message,
        temperature=0.1,   # Near-deterministic: scoring must be consistent
    )

    return _extract_json(raw)


# ─────────────────────────────────────────────────────────────────────────────
# FUNCTION 2 — generate_content
# ─────────────────────────────────────────────────────────────────────────────

def generate_content(content_type: str, content_generation_command: dict) -> str:
    """
    Generates a human-facing document based on the analysis agent's command.

    Args:
        content_type (str): One of:
            "email_to_parent" | "email_to_student" |
            "one_to_one_conversation" | "counsellor_report"

        content_generation_command (dict): The content_generation_command block
            from student_summary() output. Expected keys:
                interventions_to_generate   (list[str])
                one_to_one_questions        (list[str])
                email_parent_brief          (str | None)
                counselling_brief           (str | None)
                tone                        (str: "supportive" | "urgent" | "neutral")
                signals_to_highlight        (list[str])

    Returns:
        str: The generated document text, ready for advisor review.

    Raises:
        ValueError:          Unsupported content_type (validated before API call).
        EnvironmentError:    GEMINI_API_KEY not set.
        requests.HTTPError:  API call failed.
    """
    if content_type not in VALID_CONTENT_TYPES:
        raise ValueError(
            f"Unsupported content_type '{content_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_CONTENT_TYPES))}"
        )

    user_message = (
        f"content_type: {content_type}\n\n"
        f"content_generation_command:\n"
        f"{json.dumps(content_generation_command, indent=2)}\n\n"
        "Write the document now. Output only the document — no preamble."
    )

    return _call_gemini(
        system_prompt=SYSTEM_PROMPT_CONTENT,
        user_message=user_message,
        temperature=0.6,   # More creative latitude for human-facing writing
    )


# ─────────────────────────────────────────────────────────────────────────────
# EXAMPLE USAGE
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sample_student = {
        # ── Current week ──────────────────────────────────────────────────────
        "E_t": 32.0,
        "A_t": 41.0,       # Assessment happened this week; set to None if not.

        # ── Flagging ──────────────────────────────────────────────────────────
        "reasons_for_flagging": "low_attendance|stopped_submitting|low_quiz_score",
        "urgency_score": 145.0,
        "risk_score": 72.0,

        # ── Historical scores ─────────────────────────────────────────────────
        "E_t_history": [78.0, 72.0, 65.0, 55.0, 44.0],   # weeks 1–5
        "A_t_history": [70.0, 63.0, 55.0],                # weeks with assessments

        # ── Class-level baselines ─────────────────────────────────────────────
        "E": 65.0,   # class avg effort
        "A": 63.0,   # class avg performance

        # ── Student cumulative averages ───────────────────────────────────────
        "e": 57.7,   # student avg effort  (mean of E_t_history + current E_t)
        "a": 57.3,   # student avg performance (mean of A_t_history + current A_t)

        # ── Deviations from class mean ────────────────────────────────────────
        "del_E": -7.3,   # e − E
        "del_A": -5.7,   # a − A

        # ── Flagging history ──────────────────────────────────────────────────
        "flagging_history": {
            "times_flagged": 2,
            "weeks_since_each_flag": [4, 1],
        },

        # ── Effort factor breakdown ───────────────────────────────────────────
        "effort_contributors_student": {
            "avg_library_visits":         0.3,
            "avg_book_borrows":           0.1,
            "avg_attendance_pct":         0.42,
            "avg_assignment_submit_rate": 0.0,
            "avg_plagiarism_free_rate":   0.95,
            "avg_quiz_attempt_rate":      0.5,
        },
        "effort_contributors_class": {
            "avg_library_visits":         1.8,
            "avg_book_borrows":           0.9,
            "avg_attendance_pct":         0.82,
            "avg_assignment_submit_rate": 0.87,
            "avg_plagiarism_free_rate":   0.91,
            "avg_quiz_attempt_rate":      0.78,
        },
    }

    print("── STEP 1: student_summary ──────────────────────────────")
    summary = student_summary(sample_student)
    print(json.dumps(summary, indent=2))

    command = summary["intervention"]["content_generation_command"]

    print("\n── STEP 2: generate_content (email_to_parent) ───────────")
    email = generate_content("email_to_parent", command)
    print(email)

    print("\n── STEP 2b: generate_content (one_to_one_conversation) ──")
    script = generate_content("one_to_one_conversation", command)
    print(script)