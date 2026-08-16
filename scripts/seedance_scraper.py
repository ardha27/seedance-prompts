#!/usr/bin/env python3
"""
Seedance prompt scraper — fetches community prompts from bestseedanceprompts.com
and stores them in a local SQLite DB with FTS5 search.

Usage:
  python3 seedance_scraper.py full    # Scrape all (initial setup)
  python3 seedance_scraper.py update  # Only fetch new prompts (cron mode)
"""

import urllib.request, re, json, time, sqlite3, os, sys
import html as htmlmod
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = 'https://bestseedanceprompts.com'
DB_PATH = os.path.expanduser('~/.hermes/data/seedance_prompts.db')


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS prompts (
        url TEXT PRIMARY KEY,
        title TEXT,
        model TEXT,
        workflow TEXT,
        original_prompt TEXT,
        description TEXT,
        categories TEXT,
        settings TEXT,
        provenance TEXT,
        word_count INTEGER,
        char_count INTEGER,
        scraped_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )''')
    conn.execute('''CREATE VIRTUAL TABLE IF NOT EXISTS prompts_fts USING fts5(
        title, original_prompt, description, categories,
        content='prompts',
        content_rowid='rowid'
    )''')
    conn.executescript('''
        CREATE TRIGGER IF NOT EXISTS prompts_ai AFTER INSERT ON prompts BEGIN
            INSERT INTO prompts_fts(rowid, title, original_prompt, description, categories)
            VALUES (new.rowid, new.title, new.original_prompt, new.description, new.categories);
        END;
        CREATE TRIGGER IF NOT EXISTS prompts_au AFTER UPDATE ON prompts BEGIN
            DELETE FROM prompts_fts WHERE rowid=old.rowid;
            INSERT INTO prompts_fts(rowid, title, original_prompt, description, categories)
            VALUES (new.rowid, new.title, new.original_prompt, new.description, new.categories);
        END;
        CREATE TRIGGER IF NOT EXISTS prompts_ad AFTER DELETE ON prompts BEGIN
            DELETE FROM prompts_fts WHERE rowid=old.rowid;
        END;
    ''')
    conn.commit()
    return conn


def fetch_detail(card_url):
    url = BASE + card_url
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        })
        resp = urllib.request.urlopen(req, timeout=15)
        raw = resp.read().decode('utf-8')
        
        detail = {'url': card_url}
        
        m = re.search(r'<h[12][^>]*>(.*?)</h[12]>', raw, re.DOTALL)
        if m:
            detail['title'] = htmlmod.unescape(re.sub(r'<[^>]+>', '', m.group(1)).strip())
        
        m = re.search(r'model-badge">(Seedance [^<]+)<', raw)
        detail['model'] = m.group(1).strip() if m else ''
        
        m = re.search(r'workflow-badge">([^<]+)<', raw)
        detail['workflow'] = m.group(1).strip() if m else ''
        
        m = re.search(r'Original prompt.*?Copy Prompt(.*?)(?:<h[2-4]|<section|<footer)', raw, re.DOTALL)
        if m:
            prompt_text = re.sub(r'<[^>]+>', ' ', m.group(1)).strip()
            prompt_text = re.sub(r'\s+', ' ', htmlmod.unescape(prompt_text))
            # Clean leaked metadata (Author/Published/Source/Categories)
            prompt_text = re.split(r'\s*Author\s+', prompt_text)[0].strip()
            detail['original_prompt'] = prompt_text
        
        m = re.search(r'<meta name="description" content="([^"]+)"', raw)
        if m:
            detail['description'] = htmlmod.unescape(m.group(1))
        
        settings = {}
        dts = re.findall(r'<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>', raw, re.DOTALL)
        for dt, dd in dts:
            k = re.sub(r'<[^>]+>', '', dt).strip().lower()
            v = re.sub(r'<[^>]+>', ' ', dd).strip()
            v = re.sub(r'\s+', ' ', htmlmod.unescape(v))
            settings[k] = v
        detail['settings'] = settings
        
        cats = re.findall(r'cat-badge">([^<]+)<', raw)
        detail['categories'] = list(dict.fromkeys(htmlmod.unescape(c.strip()) for c in cats))
        
        m = re.search(r'[Pp]rovenance(.*?)(?:</dd|</dl)', raw, re.DOTALL)
        if m:
            detail['provenance'] = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', m.group(1))).strip()
        
        return detail
    except Exception as e:
        return {'url': card_url, 'error': str(e)}


def collect_card_urls():
    categories = [
        '/categories/action-fight-scenes',
        '/categories/cinematic-film',
        '/categories/music-dance',
        '/categories/commercial-product',
        '/categories/romance-drama',
        '/categories/anime-manga',
        '/categories/nature-animals',
        '/categories/dark-fantasy-horror',
        '/categories/historical-cultural',
        '/categories/tutorials-tips',
        '/categories/comedy-satire',
        '/categories/other',
        '/categories/superheroes-crossovers',
    ]
    
    all_urls = {}
    for cat_path in categories:
        url = BASE + cat_path
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            resp = urllib.request.urlopen(req, timeout=15)
            raw = resp.read().decode('utf-8')
            links = re.findall(r'<h3[^>]*>\s*<a href="(/prompts/[^"]+)">([^<]+)</a>', raw)
            for u, t in links:
                if u not in all_urls:
                    all_urls[u] = htmlmod.unescape(t)
        except:
            pass
        time.sleep(0.2)
    
    try:
        req = urllib.request.Request(BASE, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=15)
        raw = resp.read().decode('utf-8')
        links = re.findall(r'<h3[^>]*>\s*<a href="(/prompts/[^"]+)">([^<]+)</a>', raw)
        for u, t in links:
            if u not in all_urls:
                all_urls[u] = htmlmod.unescape(t)
    except:
        pass
    
    return all_urls


def upsert_to_db(conn, detail):
    if detail.get('error') or not detail.get('original_prompt'):
        return False
    
    prompt = detail.get('original_prompt', '')
    conn.execute('''INSERT INTO prompts (url, title, model, workflow, original_prompt, description,
                     categories, settings, provenance, word_count, char_count, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                     ON CONFLICT(url) DO UPDATE SET
                     title=excluded.title, model=excluded.model, workflow=excluded.workflow,
                     original_prompt=excluded.original_prompt, description=excluded.description,
                     categories=excluded.categories, settings=excluded.settings,
                     provenance=excluded.provenance, word_count=excluded.word_count,
                     char_count=excluded.char_count, updated_at=datetime('now')''',
                  (detail['url'], detail.get('title', ''), detail.get('model', ''),
                   detail.get('workflow', ''), prompt, detail.get('description', ''),
                   json.dumps(detail.get('categories', [])), json.dumps(detail.get('settings', {})),
                   detail.get('provenance', ''), len(prompt.split()), len(prompt)))
    return True


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'update'
    
    conn = init_db()
    existing = set(r[0] for r in conn.execute('SELECT url FROM prompts').fetchall())
    
    all_urls = collect_card_urls()
    
    if mode == 'update':
        to_fetch = [u for u in all_urls if u not in existing]
        if not to_fetch:
            # Silent — no output means cron stays quiet
            conn.close()
            return
    else:
        to_fetch = list(all_urls.keys())
    
    success = 0
    errors = 0
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fetch_detail, url): url for url in to_fetch}
        for future in as_completed(futures):
            detail = future.result()
            if upsert_to_db(conn, detail):
                success += 1
            else:
                errors += 1
    
    conn.commit()
    
    if success > 0:
        total = conn.execute('SELECT count(*) FROM prompts').fetchone()[0]
        print(f"Seedance DB updated: +{success} new prompts (total: {total})")
    
    conn.close()


if __name__ == '__main__':
    main()
