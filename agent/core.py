import os
from google import genai
from google.genai import types
from PIL import Image

from tools.definitions import TOOL_DEFINITIONS
from tools.executor import execute_tool, set_dependencies
from agent.models import select_model
from agent.prompts import build_system_prompt
from agent.intent import has_design_intent, is_figma_configured
from memory.manager import MemoryManager
from planner.task_planner import TaskPlanner

MAX_ITERATIONS = 50


class AgentStopped(Exception):
    """Raised when the agent is stopped mid-build."""
    pass


class AgentCore:
    def __init__(self, memory: MemoryManager):
        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        self.memory = memory
        self.planner = TaskPlanner()
        self.iteration_count = 0
        self._stop_requested = False

        # Inject shared instances into executor
        set_dependencies(memory=self.memory, planner=self.planner)

    def stop(self):
        """Request the agent to stop after the current tool call finishes."""
        self._stop_requested = True

    def _build_tools(self):
        """Convert tool definitions to Gemini function declarations."""
        declarations = []
        for tool in TOOL_DEFINITIONS:
            declarations.append(
                types.FunctionDeclaration(
                    name=tool["name"],
                    description=tool["description"],
                    parameters=tool["parameters"],
                )
            )
        return types.Tool(function_declarations=declarations)

    def run(self, user_input: str) -> str:
        """Main entry point. Runs the agentic loop until completion."""

        # Load relevant context from long-term memory
        memory_context = self.memory.get_relevant_context(user_input)

        # Determine Figma mode based on configuration and user intent
        if is_figma_configured() and has_design_intent(user_input):
            figma_mode = "active"
        elif is_figma_configured():
            figma_mode = "available"
        else:
            figma_mode = "none"
        print(f"  Figma mode: {figma_mode}")

        system_prompt = build_system_prompt(memory_context, figma_mode=figma_mode)

        model_name = select_model(self.planner.current_phase())
        print(f"  Using model: {model_name}")

        # Create chat config with tools and system instruction
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[self._build_tools()],
        )

        # Start a chat session
        chat = self.client.chats.create(model=model_name, config=config)
        self.iteration_count = 0

        # Send initial user message
        current_input = user_input
        self._stop_requested = False

        while self.iteration_count < MAX_ITERATIONS:
            # Check stop flag at the start of each iteration
            if self._stop_requested:
                print("  Build stopped by user.")
                raise AgentStopped("Build stopped by user.")

            self.iteration_count += 1
            phase = self.planner.current_phase()
            print(f"  [{phase}] Iteration {self.iteration_count}")

            response = chat.send_message(current_input)

            # Check for function calls in the response
            function_calls = []
            text_parts = []

            if response.candidates and response.candidates[0].content:
                for part in response.candidates[0].content.parts:
                    if part.function_call:
                        function_calls.append(part.function_call)
                    if part.text:
                        text_parts.append(part.text)

            # Print any text from the model
            for text in text_parts:
                print(f"  Agent: {text[:200]}")

            # If no function calls, the agent is done
            if not function_calls:
                final_text = "\n".join(text_parts)
                self.memory.save_session(user_input, final_text)
                return final_text

            # Process ALL function calls, collect responses
            function_response_parts = []
            figma_images = []

            for fc in function_calls:
                name = fc.name
                args = dict(fc.args) if fc.args else {}
                print(f"  -> Tool: {name}({_summarize_inputs(args)})")

                try:
                    result = execute_tool(name, args)
                except Exception as e:
                    print(f"  -> ERROR: {e}")
                    result = f"ERROR: {str(e)}"

                # Check if result contains image paths (Figma or validation screenshots)
                result_str = str(result)
                if "__FIGMA_IMAGES__:" in result_str:
                    marker = result_str.split("__FIGMA_IMAGES__:")[1].strip()
                    image_paths = [p.strip() for p in marker.split(",") if p.strip()]
                    for img_path in image_paths:
                        if os.path.exists(img_path):
                            figma_images.append(img_path)
                            print(f"  -> Loaded Figma screenshot: {os.path.basename(img_path)}")
                    # Remove the marker from the result text
                    result_str = result_str.split("__FIGMA_IMAGES__:")[0].strip()

                if "__VALIDATION_IMAGES__:" in result_str:
                    marker = result_str.split("__VALIDATION_IMAGES__:")[1].strip()
                    image_paths = [p.strip() for p in marker.split(",") if p.strip()]
                    for img_path in image_paths:
                        if os.path.exists(img_path):
                            figma_images.append(img_path)
                            print(f"  -> Loaded validation screenshot: {os.path.basename(img_path)}")
                    result_str = result_str.split("__VALIDATION_IMAGES__:")[0].strip()

                function_response_parts.append(
                    types.Part.from_function_response(
                        name=name,
                        response={"result": result_str},
                    )
                )

            # Check stop after processing tools
            if self._stop_requested:
                print("  Build stopped by user.")
                raise AgentStopped("Build stopped by user.")

            # If we have images (Figma or validation), send them alongside function responses
            # so Gemini can actually SEE the designs
            if figma_images:
                all_parts = list(function_response_parts)

                # Separate app screenshots from Figma screenshots by path
                app_imgs = [p for p in figma_images if "validation_screenshots" in p]
                figma_only = [p for p in figma_images if "validation_screenshots" not in p]

                has_both = app_imgs and figma_only

                if has_both:
                    # PAIRED COMPARISON: send Figma→App pairs page by page
                    # The validator sends them alternating: figma, app, figma, app, ...
                    all_parts.append(types.Part.from_text(
                        text="PAGE-BY-PAGE COMPARISON: For each page below, "
                        "the FIRST image is the FIGMA DESIGN (target) and "
                        "the SECOND image is the APP (what was built)."
                    ))

                    pair_num = 0
                    i = 0
                    while i < len(figma_images):
                        img_path = figma_images[i]
                        is_figma = "validation_screenshots" not in img_path
                        is_app = "validation_screenshots" in img_path

                        # Check if this is a paired sequence (figma then app)
                        if is_figma and i + 1 < len(figma_images) and "validation_screenshots" in figma_images[i + 1]:
                            pair_num += 1
                            all_parts.append(types.Part.from_text(
                                text=f"--- PAGE {pair_num} ---"
                            ))
                            # Figma image
                            try:
                                img = Image.open(img_path)
                                all_parts.append(img)
                                all_parts.append(types.Part.from_text(
                                    text=f"[FIGMA TARGET] {os.path.basename(img_path)}"
                                ))
                            except Exception as e:
                                print(f"  -> Could not load image {img_path}: {e}")
                            # App image
                            try:
                                img = Image.open(figma_images[i + 1])
                                all_parts.append(img)
                                all_parts.append(types.Part.from_text(
                                    text=f"[APP ACTUAL] {os.path.basename(figma_images[i + 1])}"
                                ))
                            except Exception as e:
                                print(f"  -> Could not load image {figma_images[i + 1]}: {e}")
                            i += 2
                        else:
                            # Unpaired image
                            label = "FIGMA (unpaired)" if is_figma else "APP (extra page)"
                            try:
                                img = Image.open(img_path)
                                all_parts.append(img)
                                all_parts.append(types.Part.from_text(
                                    text=f"[{label}] {os.path.basename(img_path)}"
                                ))
                            except Exception as e:
                                print(f"  -> Could not load image {img_path}: {e}")
                            i += 1

                    all_parts.append(types.Part.from_text(
                        text="For EACH page pair above, compare FIGMA TARGET vs APP ACTUAL. "
                        "List EVERY difference you find:\n"
                        "1. FONTS: wrong family, size, weight, line-height, letter-spacing?\n"
                        "2. COLORS: wrong text color, background, border color?\n"
                        "3. LAYOUT: wrong flex direction, gap, padding, alignment, spacing?\n"
                        "4. RADIUS: wrong border-radius values?\n"
                        "5. SHADOWS: missing or wrong box-shadow?\n"
                        "6. CONTENT: missing text, wrong text, missing elements?\n"
                        "7. SIZING: wrong width, height, or proportions?\n"
                        "8. MISSING PAGES: any Figma frames without an app page?\n\n"
                        "Fix EVERY difference using create_file, then call validate_screenshots again."
                    ))
                elif figma_only:
                    # Initial build — just show Figma frames to replicate
                    all_parts.append(types.Part.from_text(
                        text="--- FIGMA DESIGN SCREENSHOTS (replicate these EXACTLY) ---"
                    ))
                    for img_path in figma_only:
                        try:
                            img = Image.open(img_path)
                            all_parts.append(img)
                            all_parts.append(types.Part.from_text(
                                text=f"Figma frame: {os.path.basename(img_path)}"
                            ))
                        except Exception as e:
                            print(f"  -> Could not load image {img_path}: {e}")
                    all_parts.append(types.Part.from_text(
                        text="Above are the Figma design screenshots. "
                        "Replicate this design EXACTLY — match colors, fonts, "
                        "spacing, layout, border radius, shadows, and overall look."
                    ))

                current_input = all_parts
            else:
                current_input = function_response_parts

        return "Agent reached maximum iteration limit."

    def reset(self):
        """Clear conversation history for a new session (keeps memory)."""
        self.planner = TaskPlanner()
        set_dependencies(memory=self.memory, planner=self.planner)
        self.iteration_count = 0
        self._stop_requested = False


def _summarize_inputs(inputs: dict) -> str:
    """Create a short summary of tool inputs for logging."""
    parts = []
    for key, value in inputs.items():
        val_str = str(value)
        if len(val_str) > 50:
            val_str = val_str[:50] + "..."
        parts.append(f"{key}={val_str}")
    return ", ".join(parts)
