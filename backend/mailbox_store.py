import os
import json
import tempfile
import uuid
from typing import Dict, Any, List, Optional
import time
import threading

class MailboxStore:
    def __init__(self, data_dir: str = "data/gum_data"):
        self.data_dir = data_dir
        self.lock = threading.Lock()
        if not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)
            
        self.mailbox_path = os.path.join(data_dir, "mailbox.json")
        self._init_files()
        
    def _init_files(self):
        if not os.path.exists(self.mailbox_path):
            self._atomic_write(self.mailbox_path, {"mails": []})

    def _atomic_write(self, path: str, data: Dict[str, Any]):
        """Atomic write using tempfile and os.replace"""
        fd, temp_path = tempfile.mkstemp(dir=self.data_dir, prefix=".tmp_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, path)
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e

    def _read_json(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            return {"mails": []}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_all_mails(self) -> List[Dict[str, Any]]:
        data = self._read_json(self.mailbox_path)
        return data.get("mails", [])

    def add_mail(self, sender: str, content: str, subject: str = "", recipient: str = "User", conversation_id: Optional[str] = None) -> str:
        with self.lock:
            mails = self.get_all_mails()
            mail_id = str(uuid.uuid4())
            
            new_mail = {
                "mail_id": mail_id,
                "sender": sender,
                "subject": subject,
                "recipient": recipient,
                "content": content,
                "timestamp": time.time(),
                "is_read": False,
                "conversation_id": conversation_id
            }
            
            mails.append(new_mail)
            self._atomic_write(self.mailbox_path, {"mails": mails})
            return mail_id

    def mark_as_read(self, mail_id: str) -> bool:
        with self.lock:
            mails = self.get_all_mails()
            found = False
            for mail in mails:
                if mail.get("mail_id") == mail_id:
                    mail["is_read"] = True
                    found = True
                    break
                    
            if found:
                self._atomic_write(self.mailbox_path, {"mails": mails})
            return found

    def get_unread_count(self) -> int:
        mails = self.get_all_mails()
        return sum(1 for mail in mails if not mail.get("is_read", False) and mail.get("recipient") == "User")

# Global singleton
_global_mailbox_store = None

def init_mailbox_store(data_dir: str = "data/gum_data"):
    global _global_mailbox_store
    _global_mailbox_store = MailboxStore(data_dir)
    return _global_mailbox_store

def get_mailbox_store() -> MailboxStore:
    global _global_mailbox_store
    if _global_mailbox_store is None:
        _global_mailbox_store = MailboxStore()
    return _global_mailbox_store
