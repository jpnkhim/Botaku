"""
botaku.database - MongoDB init + async wrappers
Fix blocking DB di event loop (CRITICAL-05)
"""
from __future__ import annotations
import asyncio
import logging
from .config import MONGO_URL

logger = logging.getLogger("telekubot")

try:
    from pymongo import MongoClient, ASCENDING
    from pymongo.errors import DuplicateKeyError, ConnectionFailure
except ImportError:
    MongoClient = None
    ASCENDING = 1
    DuplicateKeyError = Exception
    ConnectionFailure = Exception

# Global collections (akan diisi init_database)
client = None
db = None
collection = None
log_collection = None
automation_collection = None
schedule_collection = None

def init_database():
    global client, db, collection, log_collection, automation_collection, schedule_collection
    if MongoClient is None:
        logger.error("pymongo not installed")
        return None, None, None
    if not MONGO_URL:
        logger.error("MONGO_URL tidak di-set!")
        return None, None, None
    try:
        client = MongoClient(
            MONGO_URL,
            serverSelectionTimeoutMS=20000,
            connectTimeoutMS=20000,
            socketTimeoutMS=20000
        )
        client.admin.command('ping')
        db = client['indonesian']
        collection = db['telegram_accounts']
        collection.create_index([("nomor_telepon", ASCENDING)], unique=True)
        log_collection = db["telegram_logs"]
        automation_collection = db["automation_tasks"]
        schedule_collection = db["automation_schedules"]
        logger.info("✅ Database connected")
        return client, db, collection
    except ConnectionFailure as e:
        logger.error(f"❌ Mongo ConnectionFailure: {e}")
        return None, None, None
    except Exception as e:
        logger.error(f"❌ DB init error: {e}")
        return None, None, None

# === Async wrappers untuk hindari blocking event loop ===
async def db_find_one(coll, *args, **kwargs):
    if coll is None:
        return None
    return await asyncio.to_thread(coll.find_one, *args, **kwargs)

async def db_find(coll, *args, **kwargs):
    if coll is None:
        return []
    return await asyncio.to_thread(lambda: list(coll.find(*args, **kwargs)))

async def db_count(coll, filter_dict=None):
    if coll is None:
        return 0
    if filter_dict is None:
        filter_dict = {}
    return await asyncio.to_thread(coll.count_documents, filter_dict)

async def db_update_one(coll, *a, **kw):
    if coll is None:
        return None
    return await asyncio.to_thread(coll.update_one, *a, **kw)

async def db_insert_one(coll, *a, **kw):
    if coll is None:
        raise RuntimeError("DB not initialized")
    return await asyncio.to_thread(coll.insert_one, *a, **kw)

async def db_delete_one(coll, *a, **kw):
    if coll is None:
        return None
    return await asyncio.to_thread(coll.delete_one, *a, **kw)

async def db_update_many(coll, *a, **kw):
    if coll is None:
        return None
    return await asyncio.to_thread(coll.update_many, *a, **kw)

def get_collections():
    return {
        "client": client,
        "db": db,
        "collection": collection,
        "log_collection": log_collection,
        "automation_collection": automation_collection,
        "schedule_collection": schedule_collection,
    }
