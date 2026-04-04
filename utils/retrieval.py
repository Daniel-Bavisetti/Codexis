def get_relevant_files(requirement: dict, codebase: dict, top_k: int = 3) -> dict:
    desc_words = set(requirement.get("description", "").lower().split())
    
    scores = []
    for path, content in codebase.items():
        content_words = set(content.lower().split())
        path_words = set(path.lower().replace(".", " ").replace("/", " ").split())
        
        # Scoring logic
        score = len(desc_words.intersection(content_words)) * 1  # Keyword overlap
        score += len(desc_words.intersection(path_words)) * 10   # Name matching
        
        # File hint heavily weighted if provided
        if requirement.get("file_hint") and requirement["file_hint"] in path:
            score += 50
            
        scores.append((score, path, content))
        
    # Sort and return top K
    scores.sort(reverse=True, key=lambda x: x[0])
    return {path: content for score, path, content in scores[:top_k]}
