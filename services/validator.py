import ast

def validate_code(file_path: str, code: str) -> tuple[bool, str]:
    if file_path.endswith(".py"):
        try:
            ast.parse(code)
            return True, "Valid Python syntax."
        except SyntaxError as e:
            return False, f"Syntax Error at line {e.lineno}: {e.msg}"
        except Exception as e:
            return False, f"Compilation Error: {str(e)}"
            
    # Fallback for other languages (JS/Java) - syntax checking omitted for POC
    return True, "Syntax validation bypassed for non-Python file."
