from agents.reviewer_agent import ReviewerAgent

agent = ReviewerAgent()

def review_code(code: str) -> dict:
    return agent.run(code)
