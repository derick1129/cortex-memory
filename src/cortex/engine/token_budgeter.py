from typing import Dict, List


class TokenBudgeter:
    def __init__(self, max_tokens: int = 2500) -> None:
        self.max_tokens = max_tokens

    def estimate_tokens(self, text: str) -> int:
        # Fast approximation: ~4 characters per token
        return max(1, len(text) // 4)

    def pack(self, items: List[Dict[str, str]]) -> str:
        packed_sections: List[str] = []
        current_tokens = 0

        for item in items:
            section_title = item.get("section", "Context")
            content = item.get("content", "").strip()
            block = f"### {section_title}\n{content}\n"
            block_tokens = self.estimate_tokens(block)

            if current_tokens + block_tokens > self.max_tokens:
                break
            packed_sections.append(block)
            current_tokens += block_tokens

        return "\n".join(packed_sections)
