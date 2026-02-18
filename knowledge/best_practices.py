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

### Smart Input Validation & Common Sense UX
Every user-facing input MUST have proper validation. Do NOT leave inputs unvalidated. Apply these automatically without being asked:

#### Email Fields
- Must contain `@` and at least one `.` after the `@`
- Show inline error: "Please enter a valid email address" on blur or submit
- Use `type="email"` on the input element
- Regex: `/^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/`

#### Name / Text Fields
- Must not be empty or whitespace-only (trim before checking)
- Minimum length check where appropriate (e.g., name >= 2 characters)
- Show inline error: "This field is required"

#### Number / Score Fields
- Validate min and max range (e.g., age 1-120, score 0-100)
- Prevent non-numeric input with `type="number"` or input filtering
- Show inline error: "Please enter a number between X and Y"

#### Password Fields (if applicable)
- Minimum 8 characters
- Show strength indicator or requirements list
- Show/hide password toggle

#### Phone Number Fields (if applicable)
- Must contain only digits, spaces, dashes, parentheses, or +
- Minimum 7 digits
- Show inline error: "Please enter a valid phone number"

#### General Validation Rules
- ALWAYS validate on blur (when user leaves the field) AND on form submit
- Show errors inline below the input (red text, ~13px, with red left border or icon)
- Disable submit button while form has errors
- Highlight invalid fields with a red border (`border-color: #e53e3e`)
- Use `aria-invalid="true"` and `aria-describedby` pointing to the error message for accessibility
- Clear the error when the user starts typing again in that field
- Prevent form submission if ANY required field is empty or invalid
- Show helpful placeholder text (e.g., "you@example.com", "Enter your name")

#### Quiz-Specific Validation
- Timer inputs: must be a positive number, reasonable range (1-120 minutes)
- Question count: must be between 1 and the total available questions
- User answer inputs (fill-in-the-blank): trim whitespace, case-insensitive comparison
- Rating scales: ensure a selection is made before proceeding

#### Error Display Pattern (React)
```jsx
const [errors, setErrors] = useState({});
// On each input: show error below it
{errors.email && <span className="field-error">{errors.email}</span>}
// CSS: .field-error { color: #e53e3e; font-size: 13px; margin-top: 4px; }
```
"""
