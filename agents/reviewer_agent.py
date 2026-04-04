import json
from utils.llm import call_llm

class ReviewerAgent:
    def run(self, code: str, requirement: dict | None = None, context: list[dict] | None = None, knowledge_graph: dict | None = None, file_path: str | None = None) -> dict:
        prompt = f"""Review this code. 
FAIL if: missing error handling, incomplete logic, bad naming, dependency violations, or security issues.
Check: logic correctness, style issues, dependency violations, and security concerns.
Target file: {file_path}
Requirement: {json.dumps(requirement or {})}
Semantic context: {json.dumps(context or [])}
Knowledge graph summary: {json.dumps({"nodes": (knowledge_graph or {}).get("nodes", [])[:20], "edges": (knowledge_graph or {}).get("edges", [])[:40]})}
        
Code:
{code}

Return EXACTLY this JSON structure, no markdown formatting:
{{
    "issues": ["list of issues"],
    "suggestions": ["list of suggestions"],
    "dependency_violations": ["list of dependency issues"],
    "security_findings": ["list of security concerns"],
    "confidence": 0.0,
    "verdict": "PASS" or "FAIL"
}}"""
        
        raw = call_llm(prompt).strip()
        if raw.startswith("```json"):
            raw = raw[7:-3].strip()
        elif raw.startswith("```"):
            raw = raw[3:-3].strip()
            
        try:
            parsed = json.loads(raw)
            parsed.setdefault("issues", [])
            parsed.setdefault("suggestions", [])
            parsed.setdefault("dependency_violations", [])
            parsed.setdefault("security_findings", [])
            parsed.setdefault("confidence", 0.5)
            parsed.setdefault("verdict", "FAIL" if parsed["issues"] else "PASS")
            return parsed
        except json.JSONDecodeError:
            return {
                "issues": ["Failed to parse LLM review output"],
                "suggestions": [],
                "dependency_violations": [],
                "security_findings": [],
                "confidence": 0.1,
                "verdict": "FAIL"
            }
