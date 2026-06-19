import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from misc.gum.gum.db_utils import search_propositions_bm25

async def test():
    engine = create_async_engine("sqlite+aiosqlite:///data/gum_data/gum.db")
    async with AsyncSession(engine) as session:
        # Without Selected Labels
        rows = await search_propositions_bm25(session, "你記得我之前對林黛玉有什麼看法嗎？", limit=10, include_deleted=False)
        print("Raw query rows:", len(rows))
        
        # With Selected Labels
        labels = {"selected_context_scopes": ["《紅樓夢》人物理解", "中國古典文學"], "selected_event_types": ["Recollection", "Personal Reflection", "Preference Expression"], "selected_targets": ["林黛玉"], "selected_functional_type_seeds": ["文學記憶", "角色認知", "主觀詮釋"]}
        rows_with_labels = await search_propositions_bm25(session, "你記得我之前對林黛玉有什麼看法嗎？", selected_labels=labels, limit=10, include_deleted=False)
        print("Rows with labels:", len(rows_with_labels))

asyncio.run(test())
