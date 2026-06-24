import json
import os
import tempfile
from typing import List, Dict, Tuple

MEMORY_DIR = os.path.join(os.path.dirname(__file__), "memories")

class MemoryStore:
    def __init__(self):
        # 為了測試 Compact 機制，我們將 USER 上限調小至 300，MEMORY 調小至 500
        # 實際應用可恢復至 2200 與 1375
        self.memory_char_limit = 500
        self.user_char_limit = 300
        self._system_prompt_snapshot: Dict[str, str] = {"memory": "", "user": ""}
        os.makedirs(MEMORY_DIR, exist_ok=True)
    
    def _get_path(self, target: str) -> str:
        return os.path.join(MEMORY_DIR, f"{target.upper()}.jsonl")
    
    def _read_jsonl(self, target: str) -> List[Dict]:
        path = self._get_path(target)
        if not os.path.exists(path):
            return []
        entries = []
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return entries

    def _write_jsonl(self, target: str, entries: List[Dict]):
        path = self._get_path(target)
        fd, temp_path = tempfile.mkstemp(dir=MEMORY_DIR, text=True)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        os.replace(temp_path, path)

    def _render_to_markdown(self, entries: List[Dict]) -> str:
        if not entries:
            return ""
        lines = []
        for entry in entries:
            content = entry.get("content", "").replace('\n', ' ')
            lines.append(f"- {content}")
        return "\n".join(lines)

    def load_from_disk(self):
        """從磁碟載入 JSONL 並渲染成 Markdown 快照，保護 Prefix Cache"""
        for target, limit in [("memory", self.memory_char_limit), ("user", self.user_char_limit)]:
            entries = self._read_jsonl(target)
            markdown = self._render_to_markdown(entries)
            
            if markdown:
                percentage = int((len(markdown) / limit) * 100)
                header = f"[{percentage}% — {len(markdown)}/{limit} chars]"
                title = "MEMORY (your personal notes)" if target == "memory" else "USER PROFILE"
                formatted = f"# {title} {header}\n{markdown}"
                self._system_prompt_snapshot[target] = formatted
            else:
                self._system_prompt_snapshot[target] = ""

    def get_snapshot(self, target: str) -> str:
        return self._system_prompt_snapshot.get(target, "")
        
    def get_raw_memories(self, target: str) -> List[str]:
        entries = self._read_jsonl(target)
        return [e.get("content", "") for e in entries]

    def _check_budget(self, target: str, new_entries: List[Dict]) -> Tuple[bool, str]:
        limit = self.memory_char_limit if target == "memory" else self.user_char_limit
        markdown = self._render_to_markdown(new_entries)
        if len(markdown) > limit:
            return False, f"Memory full: {len(markdown)} exceeds limit of {limit} chars."
        return True, ""

    def add(self, target: str, content: str) -> Dict:
        entries = self._read_jsonl(target)
        new_entries = entries + [{"content": content}]
        ok, err = self._check_budget(target, new_entries)
        if not ok:
            return {"success": False, "error": err, "current_entries": self.get_raw_memories(target)}
        self._write_jsonl(target, new_entries)
        return {"success": True, "message": "Entry added."}

    def replace(self, target: str, old_text: str, new_content: str) -> Dict:
        entries = self._read_jsonl(target)
        found = False
        new_entries = []
        for e in entries:
            if old_text in e.get("content", "") and not found:
                new_entries.append({"content": new_content})
                found = True
            else:
                new_entries.append(e)
        if not found:
            return {"success": False, "error": f"Text '{old_text}' not found."}
        ok, err = self._check_budget(target, new_entries)
        if not ok:
            return {"success": False, "error": err, "current_entries": self.get_raw_memories(target)}
        self._write_jsonl(target, new_entries)
        return {"success": True, "message": "Entry replaced."}

    def remove(self, target: str, old_text: str) -> Dict:
        entries = self._read_jsonl(target)
        new_entries = [e for e in entries if old_text not in e.get("content", "")]
        if len(new_entries) == len(entries):
            return {"success": False, "error": f"Text '{old_text}' not found."}
        self._write_jsonl(target, new_entries)
        return {"success": True, "message": "Entry removed."}

    def overwrite_memories(self, target: str, contents: List[str]) -> Dict:
        """供 Compact 機制使用，以整理後的新清單覆寫檔案"""
        new_entries = [{"content": c} for c in contents]
        ok, err = self._check_budget(target, new_entries)
        if not ok:
            return {"success": False, "error": f"即使壓縮後仍超出預算: {err}"}
        self._write_jsonl(target, new_entries)
        return {"success": True, "message": "Memories overwritten (compacted)."}
