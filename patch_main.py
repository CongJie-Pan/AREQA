import re
import sys

def patch():
    with open('/workspaces/AREQA/backend/main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Import get_current_user
    if 'from auth import get_current_user' not in content:
        content = content.replace('from fastapi import FastAPI, Request, WebSocket, HTTPException\n', 'from fastapi import FastAPI, Request, WebSocket, HTTPException, Depends\nfrom auth import get_current_user\n')
    
    # 1. fetch_memory
    content = content.replace(
        '@app.get("/api/v1/memory")\nasync def fetch_memory():',
        '@app.get("/api/v1/memory")\nasync def fetch_memory(current_user_id: str = Depends(get_current_user)):'
    )
    
    # 2. get_memory_summary
    content = content.replace(
        '@app.get("/api/v1/memory/summary")\nasync def get_memory_summary():',
        '@app.get("/api/v1/memory/summary")\nasync def get_memory_summary(current_user_id: str = Depends(get_current_user)):'
    )
    
    # 3. fetch_mailbox
    content = content.replace(
        '@app.get("/api/v1/mailbox")\nasync def fetch_mailbox():\n    store = get_mailbox_store()\n    return {\n        "mails": await store.get_all_mails("default_user"),\n        "unread_count": await store.get_unread_count("default_user")\n    }',
        '@app.get("/api/v1/mailbox")\nasync def fetch_mailbox(current_user_id: str = Depends(get_current_user)):\n    store = get_mailbox_store()\n    return {\n        "mails": await store.get_all_mails(current_user_id),\n        "unread_count": await store.get_unread_count(current_user_id)\n    }'
    )
    
    # 4. send_mail_endpoint
    content = content.replace(
        '@app.post("/api/v1/mailbox/send")\nasync def send_mail_endpoint(req: SendMailRequest):\n    store = get_mailbox_store()\n    mail_id = await store.add_mail(user_id="default_user", sender="User", content=req.content, recipient=req.recipient, conversation_id=req.conversation_id)\n    await store.mark_as_read(user_id="default_user", mail_id=mail_id)',
        '@app.post("/api/v1/mailbox/send")\nasync def send_mail_endpoint(req: SendMailRequest, current_user_id: str = Depends(get_current_user)):\n    store = get_mailbox_store()\n    mail_id = await store.add_mail(user_id=current_user_id, sender="User", content=req.content, recipient=req.recipient, conversation_id=req.conversation_id)\n    await store.mark_as_read(user_id=current_user_id, mail_id=mail_id)'
    )
    
    # 5. read_mail_endpoint
    content = content.replace(
        '@app.post("/api/v1/mailbox/read/{mail_id}")\nasync def read_mail_endpoint(mail_id: str):\n    store = get_mailbox_store()\n    success = await store.mark_as_read(user_id="default_user", mail_id=mail_id)',
        '@app.post("/api/v1/mailbox/read/{mail_id}")\nasync def read_mail_endpoint(mail_id: str, current_user_id: str = Depends(get_current_user)):\n    store = get_mailbox_store()\n    success = await store.mark_as_read(user_id=current_user_id, mail_id=mail_id)'
    )
    
    # 6. delete_memory_endpoint
    content = re.sub(
        r'@app\.delete\("/api/v1/memory/\{mem_id\}"\)\nasync def delete_memory_endpoint\(mem_id: str\):(.*?)await store\.redis\.set\("areqa:user_profile:default_user", json\.dumps\(profile, ensure_ascii=False\)\)(.*?)await store\.redis\.set\("areqa:hot_memory:default_user", json\.dumps\(hot_mem, ensure_ascii=False\)\)',
        r'@app.delete("/api/v1/memory/{mem_id}")\nasync def delete_memory_endpoint(mem_id: str, current_user_id: str = Depends(get_current_user)):\1await store.redis.set(f"areqa:user_profile:{current_user_id}", json.dumps(profile, ensure_ascii=False))\2await store.redis.set(f"areqa:hot_memory:{current_user_id}", json.dumps(hot_mem, ensure_ascii=False))',
        content,
        flags=re.DOTALL
    )
    content = content.replace('profile = await store.get_user_profile("default_user")', 'profile = await store.get_user_profile(current_user_id)')
    content = content.replace('hot_mem = await store.get_hot_memory("default_user")', 'hot_mem = await store.get_hot_memory(current_user_id)')
    
    # 7. batch_delete_memory_endpoint
    content = content.replace(
        '@app.post("/api/v1/memory/batch-delete")\nasync def batch_delete_memory_endpoint(req: DeleteBatchRequest):\n    for mem_id in req.ids:\n        await delete_memory_endpoint(mem_id)',
        '@app.post("/api/v1/memory/batch-delete")\nasync def batch_delete_memory_endpoint(req: DeleteBatchRequest, current_user_id: str = Depends(get_current_user)):\n    for mem_id in req.ids:\n        await delete_memory_endpoint(mem_id, current_user_id)'
    )
    
    # 8. edit_memory_endpoint
    edit_mem_old = """@app.put("/api/v1/memory/{mem_id}")
async def edit_memory_endpoint(mem_id: str, req: EditMemoryRequest):"""
    edit_mem_new = """@app.put("/api/v1/memory/{mem_id}")
async def edit_memory_endpoint(mem_id: str, req: EditMemoryRequest, current_user_id: str = Depends(get_current_user)):"""
    content = content.replace(edit_mem_old, edit_mem_new)

    pgvector_update_old = """                    if embed:
                        import struct
                        embed_bytes = struct.pack(f'{len(embed)}f', *embed)
                        with cold_retriever._get_conn() as conn:
                            conn.execute("UPDATE propositions_fts SET text = ? WHERE rowid = ?", (req.text, int(mem_id)))
                            conn.execute("UPDATE vec_memory SET embedding = ? WHERE id = ?", (embed_bytes, int(mem_id)))
                            conn.commit()"""
    
    pgvector_update_new = """                    if embed:
                        from cold_memory import get_engine
                        from sqlalchemy import text
                        from sqlalchemy.ext.asyncio import AsyncSession
                        engine = get_engine()
                        async with AsyncSession(engine) as session:
                            async with session.begin():
                                await session.execute(text(
                                    "SELECT set_config('request.jwt.claims', "
                                    "jsonb_build_object('role', 'authenticated', 'sub', :uid)::text, TRUE)"
                                ), {"uid": current_user_id})
                                await session.execute(text("SET LOCAL ROLE authenticated;"))
                                
                                await session.execute(text("UPDATE propositions SET text = :text WHERE id = :id"), {"text": req.text, "id": int(mem_id)})
                                await session.execute(text("UPDATE vec_memory SET embedding = :emb::vector WHERE id = :id"), {"emb": str(embed), "id": int(mem_id)})"""
    
    content = content.replace(pgvector_update_old, pgvector_update_new)
    
    content = content.replace('await store.redis.set("areqa:user_profile:default_user",', 'await store.redis.set(f"areqa:user_profile:{current_user_id}",')
    content = content.replace('await store.redis.set("areqa:hot_memory:default_user",', 'await store.redis.set(f"areqa:hot_memory:{current_user_id}",')
    
    with open('/workspaces/AREQA/backend/main.py', 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == '__main__':
    patch()
