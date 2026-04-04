import json
from utils.llm import call_llm

class GeneratorAgent:
    def _clean_code(self, raw: str) -> str:
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            return "\n".join(lines[1:-1]).strip() if len(lines) >= 2 else raw
        return raw

    def generate(
        self,
        requirement: dict,
        context: list[dict],
        ast: dict,
        mode: str,
        feedback: str = None,
        past_rejections: str = None,
        knowledge_graph: dict | None = None,
        learning_context: dict | None = None,
    ) -> dict:
        file_hint = requirement.get('file_hint', 'new_module.py')
        ctx_str = "\n\n".join(
            [
                f"--- {item['path']} :: {item.get('symbol', '__file__')} ({item.get('kind', 'file')}, score={item.get('score', 0)}) ---\n{item['content']}"
                for item in context
            ]
        )
        graph_summary = json.dumps(
            {
                "nodes": knowledge_graph.get("nodes", [])[:40] if knowledge_graph else [],
                "edges": knowledge_graph.get("edges", [])[:80] if knowledge_graph else [],
            }
        )
        prompt = f"""Mode: {mode}
Requirement: {json.dumps(requirement)}
Target File: {file_hint}

Semantic AST: {json.dumps(ast.get('modules', []))}
Knowledge Graph: {graph_summary}
Learning Context: {json.dumps(learning_context or {})}

Relevant Context Files:
{ctx_str}
"""
        if mode == "FIT":
            prompt += "\nTask: Analyze only. Return JSON: {\"summary\": \"...\", \"coverage\": \"FULL|PARTIAL|NONE\", \"gaps\": []}"
        elif mode == "PARTIAL":
            prompt += "\nTask: Modify existing code. Respect dependencies and existing module boundaries. Return ONLY the complete updated raw code. No diffs. No markdown."
        elif mode == "GAP":
            prompt += "\nTask: Generate completely new code. Keep interfaces explicit and safe. Return ONLY the complete raw code. No diffs. No markdown."
            
        if past_rejections:
            prompt += f"\n\nLEARNING: This change was previously rejected by the user. Do NOT repeat these mistakes:\n{past_rejections}"
            
        if feedback:
            prompt += f"\n\nWARNING: Review failed. Fix these issues immediately:\n{feedback}"
            
        raw_response = call_llm(prompt)
        
        if mode == "FIT":
            if raw_response.startswith("```json"): raw_response = raw_response[7:-3]
            elif raw_response.startswith("```"): raw_response = raw_response[3:-3]
            return {"file": file_hint, "output": raw_response.strip(), "mode": mode}
        
        return {"file": file_hint, "output": self._clean_code(raw_response), "mode": mode}
