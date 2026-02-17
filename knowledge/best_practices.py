QUIZ_UX_GUIDELINES = """
## Quiz App UX Best Practices

### Visual Design
- Use a gradient or solid color background (avoid plain white)
- Card-based layout for questions (rounded corners, subtle shadow)
- Minimum 16px font size for question text, 14px for options
- High contrast between text and background (WCAG AA minimum)
- Smooth transitions between screens (CSS transitions, 300ms)

### Interaction Design
- Highlight selected option clearly (color change + scale transform)
- Disable "Next" button until an option is selected
- Show progress: either a progress bar or "Question X of Y"
- Provide immediate visual feedback on selection
- Make the primary action button large and obvious

### Mobile Responsiveness
- Full-width options on mobile (no side-by-side layout below 640px)
- Minimum 44px touch targets for all interactive elements
- Stack layout vertically on small screens
- Use viewport meta tag for proper scaling

### Accessibility
- All interactive elements must be keyboard-navigable
- Use semantic HTML (button, not div with onclick)
- Include aria-labels for icon-only buttons
- Ensure color is not the only indicator (add icons or text)
- Support prefers-reduced-motion for animations

### Performance
- Inline critical CSS or use a single external stylesheet
- No external dependencies (no CDN calls)
- All quiz data embedded in JS (no fetch calls needed)
- Keep total page weight under 100KB
"""
