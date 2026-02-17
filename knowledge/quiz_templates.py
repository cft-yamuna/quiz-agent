TRIVIA_TEMPLATE = {
    "type": "trivia",
    "description": "Multiple-choice with right/wrong answers and scoring",
    "structure": {
        "html": "Start screen -> Question screen (with progress bar) -> Results screen (with score)",
        "data_format": {
            "questions": [
                {
                    "id": 1,
                    "question": "...",
                    "options": ["A", "B", "C", "D"],
                    "correct": 0,
                    "explanation": "...",
                }
            ]
        },
        "features": [
            "Score tracking (correct/total)",
            "Progress bar",
            "Answer feedback (correct/incorrect with explanation)",
            "Final score with percentage and rating",
            "Option to retry",
        ],
        "scoring": "1 point per correct answer, show percentage at end",
    },
}

PERSONALITY_TEMPLATE = {
    "type": "personality",
    "description": "No right/wrong answers; maps responses to personality profiles",
    "structure": {
        "html": "Start screen -> Question screen -> Profile result screen",
        "data_format": {
            "questions": [
                {
                    "id": 1,
                    "question": "...",
                    "options": [
                        {"text": "...", "scores": {"profile_a": 2, "profile_b": 0}},
                        {"text": "...", "scores": {"profile_a": 0, "profile_b": 2}},
                    ],
                }
            ],
            "profiles": {
                "profile_a": {
                    "name": "...",
                    "description": "...",
                    "emoji": "...",
                },
                "profile_b": {
                    "name": "...",
                    "description": "...",
                    "emoji": "...",
                },
            },
        },
        "features": [
            "No correct/incorrect feedback",
            "Score accumulation per profile",
            "Profile result with description and matching percentage",
            "Shareable result card",
        ],
        "scoring": "Accumulate points per profile, highest wins",
    },
}

EDUCATIONAL_TEMPLATE = {
    "type": "educational",
    "description": "Learning-focused with detailed explanations",
    "structure": {
        "html": "Start screen -> Question screen (with learn mode toggle) -> Summary screen",
        "data_format": {
            "questions": [
                {
                    "id": 1,
                    "question": "...",
                    "options": ["A", "B", "C", "D"],
                    "correct": 0,
                    "explanation": "Detailed explanation of WHY this is correct...",
                    "source": "Optional reference/citation",
                }
            ]
        },
        "features": [
            "Immediate feedback with explanation after each question",
            "Cannot proceed until viewing explanation",
            "Summary of all questions with explanations at end",
            "Track areas of strength and weakness",
            "Option to review incorrect answers",
        ],
        "scoring": "Score + learning summary with weak areas highlighted",
    },
}

EXAM_TEMPLATE = {
    "type": "exam",
    "description": "Timed assessment with pass/fail",
    "structure": {
        "html": "Start screen (with rules) -> Timed question screen -> Detailed results",
        "data_format": {
            "questions": [
                {
                    "id": 1,
                    "question": "...",
                    "options": ["A", "B", "C", "D"],
                    "correct": 0,
                    "points": 1,
                    "category": "Topic area",
                }
            ],
            "config": {
                "time_limit_minutes": 30,
                "pass_percentage": 70,
                "allow_review": False,
                "shuffle_questions": True,
            },
        },
        "features": [
            "Countdown timer (prominent display)",
            "Auto-submit when time expires",
            "No going back to previous questions (optional)",
            "Question flagging for review",
            "Detailed results by category",
            "Pass/fail determination",
        ],
        "scoring": "Weighted scoring, pass/fail threshold",
    },
}

ALL_TEMPLATES = {
    "trivia": TRIVIA_TEMPLATE,
    "personality": PERSONALITY_TEMPLATE,
    "educational": EDUCATIONAL_TEMPLATE,
    "exam": EXAM_TEMPLATE,
}
