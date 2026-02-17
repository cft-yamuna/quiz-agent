import os
from google import genai
from google.genai import types
from PIL import Image

from tools.definitions import TOOL_DEFINITIONS
from tools.executor import execute_tool, set_dependencies
from agent.models import select_model
from agent.prompts import build_system_prompt
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
        system_prompt = build_system_prompt(memory_context)

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

                # Check if result contains Figma image paths
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

            # If we have Figma images, send them alongside the function responses
            # so Gemini can actually SEE the design
            if figma_images:
                all_parts = list(function_response_parts)
                for img_path in figma_images:
                    try:
                        img = Image.open(img_path)
                        all_parts.append(img)
                    except Exception as e:
                        print(f"  -> Could not load image {img_path}: {e}")
                all_parts.append(types.Part.from_text(
                    "Above are the actual Figma design screenshots. "
                    "Replicate this visual design EXACTLY — match the colors, "
                    "fonts, spacing, layout, border radius, shadows, and overall look. "
                    "The generated quiz app must look like these screenshots."
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
