import os
import google.generativeai as genai

from tools.definitions import TOOL_DEFINITIONS
from tools.executor import execute_tool, set_dependencies
from agent.models import select_model
from agent.prompts import build_system_prompt
from memory.manager import MemoryManager
from planner.task_planner import TaskPlanner

MAX_ITERATIONS = 50


class AgentCore:
    def __init__(self, memory: MemoryManager):
        # Configure Gemini with API key from environment
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

        self.memory = memory
        self.planner = TaskPlanner()
        self.chat = None
        self.iteration_count = 0

        # Inject shared instances into executor
        set_dependencies(memory=self.memory, planner=self.planner)

    def _build_tools(self):
        """Convert tool definitions to Gemini function declarations."""
        declarations = []
        for tool in TOOL_DEFINITIONS:
            declarations.append(
                genai.protos.FunctionDeclaration(
                    name=tool["name"],
                    description=tool["description"],
                    parameters=tool["parameters"],
                )
            )
        return genai.protos.Tool(function_declarations=declarations)

    def _create_model(self, system_prompt: str):
        """Create a Gemini GenerativeModel with tools and system instruction."""
        model_name = select_model(self.planner.current_phase())
        print(f"  Using model: {model_name}")

        model = genai.GenerativeModel(
            model_name=model_name,
            tools=[self._build_tools()],
            system_instruction=system_prompt,
        )
        return model

    def run(self, user_input: str) -> str:
        """Main entry point. Runs the agentic loop until completion."""

        # Load relevant context from long-term memory
        memory_context = self.memory.get_relevant_context(user_input)
        system_prompt = build_system_prompt(memory_context)

        # Create model and start chat
        model = self._create_model(system_prompt)
        self.chat = model.start_chat()
        self.iteration_count = 0

        # Send initial user message
        current_input = user_input

        while self.iteration_count < MAX_ITERATIONS:
            self.iteration_count += 1
            phase = self.planner.current_phase()
            print(f"  [{phase}] Iteration {self.iteration_count}")

            response = self.chat.send_message(current_input)

            # Check for function calls in the response
            function_calls = []
            text_parts = []

            for part in response.parts:
                if part.function_call:
                    function_calls.append(part.function_call)
                elif part.text:
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
            function_responses = []
            for fc in function_calls:
                name = fc.name
                args = dict(fc.args)
                print(f"  -> Tool: {name}({_summarize_inputs(args)})")

                try:
                    result = execute_tool(name, args)
                except Exception as e:
                    print(f"  -> ERROR: {e}")
                    result = f"ERROR: {str(e)}"

                function_responses.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=name,
                            response={"result": str(result)},
                        )
                    )
                )

            # Send all function responses back to continue the loop
            current_input = function_responses

        return "Agent reached maximum iteration limit."

    def reset(self):
        """Clear conversation history for a new session (keeps memory)."""
        self.chat = None
        self.planner = TaskPlanner()
        set_dependencies(memory=self.memory, planner=self.planner)
        self.iteration_count = 0


def _summarize_inputs(inputs: dict) -> str:
    """Create a short summary of tool inputs for logging."""
    parts = []
    for key, value in inputs.items():
        val_str = str(value)
        if len(val_str) > 50:
            val_str = val_str[:50] + "..."
        parts.append(f"{key}={val_str}")
    return ", ".join(parts)
