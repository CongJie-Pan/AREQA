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

    async def add_mail(
        self,
        user_id: str,
        sender: str,
        content: str,
        subject: str = "",
        recipient: str = "User",
        conversation_id: Optional[str] = None,
        mail_id: Optional[str] = None,
        delivered_task_id: Optional[str] = None,
    ) -> str:
        mails = await self.get_all_mails(user_id)

        if delivered_task_id:
            for mail in mails:
                if mail.get("delivered_task_id") == delivered_task_id:
                    return mail["mail_id"]

        mail_id = mail_id or str(uuid.uuid4())
        
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
        if delivered_task_id:
            new_mail["delivered_task_id"] = delivered_task_id
        
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
        mail_data = dict(mail_data)
        mail_data.setdefault("task_id", str(uuid.uuid4()))
        mail_data["user_id"] = user_id
        score = time.time() + delay_seconds
        mail_data_json = json.dumps(mail_data, ensure_ascii=False)
        await self.redis.zadd(f"areqa:delayed_mail:{user_id}", {mail_data_json: score})
        logger.info(f"[MailboxStore] Added delayed mail task {mail_data['task_id']} for user {user_id} with delay {delay_seconds}s")
        return mail_data["task_id"]

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
            cursor = 0
            while True:
                cursor, keys = await redis.scan(cursor=cursor, match="areqa:delayed_mail:*", count=100)
                for key in keys:
                    tasks = await redis.zrangebyscore(key, 0, now)
                    for task_json in tasks:
                        task = json.loads(task_json)
                        user_id = task.get("user_id", "default_user")
                        task_id = task.get("task_id") or task.get("mail_id") or task_json
                        lock_key = f"areqa:delayed_mail_lock:{task_id}"
                        if not await redis.set(lock_key, "1", nx=True, ex=300):
                            continue

                        active_avatar = task.get("active_avatar", "AREQA")
                        conversation_id = task.get("conversation_id")
                        subject = task.get("subject") or ""
                        content = task.get("content") or ""

                        if not content:
                            from gum_integration import (
                                generate_epistolary_letter_via_llm,
                                get_hot_memory_snapshot,
                                query_cold_memory_for_context,
                            )

                            reply_content = task.get("reply_content", "")
                            snapshot = await get_hot_memory_snapshot(user_id)
                            hot_context = f"使用者的回信內容：{reply_content}\n---\n目前對話脈絡：\n{snapshot}"
                            event_summary = f"使用者回信給 {active_avatar} 探討：{reply_content[:50]}"
                            cold_ctx = await query_cold_memory_for_context(user_id, event_summary)
                            subject, content = await generate_epistolary_letter_via_llm(
                                user_id=user_id,
                                active_avatar=active_avatar,
                                hot_memory_snapshot=hot_context,
                                cold_memory_context=cold_ctx,
                            )
                        
                        store = get_mailbox_store()
                        await store.add_mail(
                            user_id=user_id,
                            sender=active_avatar,
                            content=content,
                            subject=subject,
                            recipient="User",
                            conversation_id=conversation_id,
                            delivered_task_id=task_id,
                        )
                        
                        # Broadcast alert (we have to import ws_manager)
                        from services.connection_manager import ws_manager
                        asyncio.create_task(ws_manager.broadcast_mail_alert(sender=active_avatar, user_id=user_id))
                        
                        await redis.zrem(key, task_json)
                        await redis.delete(lock_key)
                        
                if cursor == 0:
                    break
                        
            await asyncio.sleep(1)
        except Exception as e:
            print(f"[Mailbox Worker] Error: {e}")
            await asyncio.sleep(5)
