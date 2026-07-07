import json
import uuid
import time
import logging
from typing import Dict, Any, List, Optional
import asyncio

from redis_client import get_redis

logger = logging.getLogger(__name__)

class MailboxStore:
    def __init__(self):
        self.redis = get_redis()

    async def get_all_mails(self, user_id: str) -> List[Dict[str, Any]]:
        # mails can be stored in a Redis list or just a JSON string of list.
        data = await self.redis.get(f"areqa:mailbox:{user_id}")
        return json.loads(data) if data else []

    async def add_mail(self, user_id: str, sender: str, content: str, subject: str = "", recipient: str = "User", conversation_id: Optional[str] = None) -> str:
        mails = await self.get_all_mails(user_id)
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
        await self.redis.set(f"areqa:mailbox:{user_id}", json.dumps(mails, ensure_ascii=False))
        return mail_id

    async def mark_as_read(self, user_id: str, mail_id: str) -> bool:
        mails = await self.get_all_mails(user_id)
        found = False
        for mail in mails:
            if mail.get("mail_id") == mail_id:
                mail["is_read"] = True
                found = True
                break
                
        if found:
            await self.redis.set(f"areqa:mailbox:{user_id}", json.dumps(mails, ensure_ascii=False))
        return found

    async def get_unread_count(self, user_id: str) -> int:
        mails = await self.get_all_mails(user_id)
        return sum(1 for mail in mails if not mail.get("is_read", False) and mail.get("recipient") == "User")

    async def schedule_delayed_mail(self, user_id: str, mail_data: Dict[str, Any], delay_seconds: int = 300):
        # We assume delay_seconds = 300
        score = time.time() + delay_seconds
        mail_data_json = json.dumps(mail_data, ensure_ascii=False)
        await self.redis.zadd(f"areqa:delayed_mail:{user_id}", {mail_data_json: score})
        logger.info(f"[MailboxStore] Enqueued delayed mail for user {user_id} with delay {delay_seconds}s")

_global_mailbox_store = None

def init_mailbox_store():
    global _global_mailbox_store
    _global_mailbox_store = MailboxStore()
    return _global_mailbox_store

def get_mailbox_store() -> MailboxStore:
    global _global_mailbox_store
    if _global_mailbox_store is None:
        init_mailbox_store()
    return _global_mailbox_store

# Background Worker for Delayed Mails
async def delayed_mail_worker():
    redis = get_redis()
    logger.info("[Mailbox Worker] Started delayed mail worker")
    while True:
        try:
            now = time.time()
            cursor = '0'
            while cursor != 0:
                cursor, keys = await redis.scan(cursor=cursor, match="areqa:delayed_mail:*", count=100)
                for key in keys:
                    tasks = await redis.zrangebyscore(key, 0, now)
                    for task_json in tasks:
                        task = json.loads(task_json)
                        # task contains: mail_id, content, active_avatar, delay_seconds, user_id
                        user_id = task.get("user_id", "default_user")
                        content = task.get("content", "")
                        active_avatar = task.get("active_avatar", "AREQA")
                        conversation_id = task.get("conversation_id")
                        subject = task.get("subject", "")
                        
                        store = get_mailbox_store()
                        await store.add_mail(user_id=user_id, sender=active_avatar, content=content, subject=subject, recipient="User", conversation_id=conversation_id)
                        
                        # Broadcast alert (we have to import ws_manager)
                        from services.connection_manager import ws_manager
                        asyncio.create_task(ws_manager.broadcast_mail_alert(active_avatar))
                        
                        await redis.zrem(key, task_json)
                        
            await asyncio.sleep(1)
        except Exception as e:
            print(f"[Mailbox Worker] Error: {e}")
            await asyncio.sleep(5)
