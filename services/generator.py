from agents.generator_agent import GeneratorAgent

agent = GeneratorAgent()

def analyze_fit(req: dict, codebase: dict) -> str:
    return agent.generate(req, [], {"modules": []}, "FIT")

def generate_code(req: dict, codebase: dict, feedback: str = None) -> dict:
    return agent.generate(req, [], {"modules": []}, req.get("type", "PARTIAL"), feedback=feedback)
