import os

def load_codebase(path: str) -> dict:
    codebase = {}
    valid_exts = {'.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.go'}
    
    if not os.path.exists(path):
        return codebase
        
    for root, _, files in os.walk(path):
        for f in files:
            if os.path.splitext(f)[1] in valid_exts:
                full_path = os.path.join(root, f)
                with open(full_path, 'r', encoding='utf-8') as file:
                    codebase[full_path] = file.read()
                    
    return codebase
