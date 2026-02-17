QUIZ_UX_GUIDELINES = """
## Quiz App UX Best Practices (React)

### Visual Design
- Use a gradient or solid color background (avoid plain white)
- Card-based layout for questions (rounded corners, subtle shadow)
- Minimum 16px font size for question text, 14px for options
- High contrast between text and background (WCAG AA minimum)
- Smooth transitions between screens (CSS transitions, 300ms)

### Interaction Design
- Highlight selected option clearly (color change + scale transform)
- Disable "Next" button until an option is selected
- Show progress: either a ProgressBar component or "Question X of Y"
- Provide immediate visual feedback on selection
- Make the primary action button large and obvious

### Mobile Responsiveness
- Full-width options on mobile (no side-by-side layout below 640px)
- Minimum 44px touch targets for all interactive elements
- Stack layout vertically on small screens
- Use viewport meta tag for proper scaling

### Accessibility
- All interactive elements must be keyboard-navigable
- Use semantic HTML elements (button, not div with onClick)
- Include aria-labels for icon-only buttons
- Ensure color is not the only indicator (add icons or text)
- Support prefers-reduced-motion for animations

### React Architecture
- Use functional components with hooks (no class components)
- Create a custom useQuiz() hook for all quiz state (currentQuestion, score, answers, phase)
- Keep components small: QuizStart, Question, ProgressBar, Results
- Put quiz data in src/data/questions.js (separate from components)
- Use react-router-dom for navigation between quiz phases
- Use CSS modules or a single App.css (no CSS-in-JS to keep deps minimal)

### Performance
- Use React.memo() for option buttons that don't change
- Use useCallback for event handlers passed to child components
- Lazy load the Results component (React.lazy + Suspense)
- All quiz data embedded in JS modules (no fetch calls needed)
"""
