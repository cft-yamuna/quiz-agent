TRIVIA_TEMPLATE = {
    "type": "trivia",
    "description": "Multiple-choice with right/wrong answers and scoring",
    "structure": {
        "components": "QuizStart -> Question (with ProgressBar) -> Results (with score)",
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
        "react_components": [
            "QuizStart.jsx — title, description, start button",
            "Question.jsx — question text, option buttons, next button",
            "ProgressBar.jsx — visual progress indicator",
            "Results.jsx — score display, percentage, retry button",
        ],
        "features": [
            "Score tracking (correct/total) via useQuiz hook",
            "Progress bar component",
            "Answer feedback (correct/incorrect with explanation)",
            "Final score with percentage and rating",
            "Option to retry (reset state)",
        ],
        "scoring": "1 point per correct answer, show percentage at end",
    },
}

PERSONALITY_TEMPLATE = {
    "type": "personality",
    "description": "No right/wrong answers; maps responses to personality profiles",
    "structure": {
        "components": "QuizStart -> Question -> ProfileResult",
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
        "react_components": [
            "QuizStart.jsx — title, personality quiz intro",
            "Question.jsx — question text, personality option cards",
            "ProfileResult.jsx — matched profile, description, share button",
        ],
        "features": [
            "No correct/incorrect feedback",
            "Score accumulation per profile via useQuiz hook",
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
        "components": "QuizStart -> Question (with learn mode) -> Summary",
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
        "react_components": [
            "QuizStart.jsx — title, learning mode toggle",
            "Question.jsx — question, options, explanation panel",
            "Explanation.jsx — detailed explanation after answering",
            "Summary.jsx — all questions reviewed, weak areas highlighted",
        ],
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
        "components": "QuizStart (rules) -> TimedQuestion -> DetailedResults",
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
        "react_components": [
            "QuizStart.jsx — rules display, start exam button",
            "TimedQuestion.jsx — question with countdown timer",
            "Timer.jsx — countdown display component",
            "DetailedResults.jsx — category breakdown, pass/fail",
        ],
        "features": [
            "Countdown timer (useEffect + setInterval)",
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
