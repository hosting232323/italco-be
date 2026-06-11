import os
import sys
import json
from datetime import datetime, timedelta

# Add root to sys.path to import src
sys.path.append(os.getcwd())

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = 'postgresql://postgres:password@localhost:5432/italco_be'
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

def get_logs():
    print("--- Logs between 2026-06-09 08:00 and 12:00 ---")
    query = text("""
        SELECT l.created_at, u.nickname, l.content 
        FROM log l 
        JOIN "user" u ON l.user_id = u.id 
        WHERE l.created_at >= '2026-06-09 08:00:00' 
          AND l.created_at <= '2026-06-09 12:00:00'
        ORDER BY l.created_at ASC
    """)
    results = session.execute(query)
    for row in results:
        content = json.loads(row.content)
        req = content.get('request', {})
        res = content.get('response', {})
        method = req.get('method')
        url = req.get('url')
        print(f"[{row.created_at}] {row.nickname}: {method} {url}")
        if method == 'PUT' and url and ('schedule' in url or 'order' in url):
            print(f"  Request Data: {json.dumps(req.get('data'))}")
            print(f"  Response: {json.dumps(res)}")

def get_order_history(order_id):
    print(f"--- History for Order {order_id} ---")
    query = text("""
        SELECT created_at, status 
        FROM history 
        WHERE order_id = :order_id 
        ORDER BY created_at ASC
    """)
    results = session.execute(query, {'order_id': order_id})
    for row in results:
        print(f"[{row.created_at}] {row.status}")

def find_order_by_addressee(name):
    print(f"--- Searching for Order with addressee like '{name}' ---")
    query = text("""
        SELECT id, addressee, status, completion_date 
        FROM "order" 
        WHERE addressee ILIKE :name
    """)
    results = session.execute(query, {'name': f'%{name}%'})
    for row in results:
        print(f"ID: {row.id}, Addressee: {row.addressee}, Status: {row.status}, Completion: {row.completion_date}")
        get_order_history(row.id)

if __name__ == "__main__":
    print("--- Searching for all orders (including deleted) ---")
    # In some systems, deleted orders are just flagged. 
    # Let's see if there is a 'deleted' column or similar.
    # I'll just query the table and see.
    query = text("SELECT id, addressee, status FROM \"order\" WHERE addressee ILIKE '%Edil%' OR addressee ILIKE '%Lubelli%'")
    results = session.execute(query)
    for row in results:
        print(f"ID: {row.id}, Addressee: {row.addressee}, Status: {row.status}")
