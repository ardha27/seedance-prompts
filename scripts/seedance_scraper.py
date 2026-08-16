#!/usr/bin/env python3
"""
Seedance prompt scraper — fetches community prompts from bestseedanceprompts.com
and stores them in a local SQLite DB with FTS5 search.

Auto-pushes updated stats & scripts to GitHub when new prompts are added.

Usage:
  python3 seedance_scraper.py full    # Scrape all (initial setup)
  python3 seedance_scraper.py update  # Only fetch new prompts (cron mode)
"""

import urllib.request, re, json, time, sqlite3, os, sys, subprocess
import html as htmlmod
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = 'https://bestseedanceprompts.com'
DB_PATH = os.path.expanduser('~/.hermes/data/seedance_prompts.db')
REPO_DIR = '/home/rishua/seedance-prompts'


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


def auto_push_github(new_count, total_count):
    """Auto-commit and push stats to GitHub if new prompts were added."""
    if not os.path.exists(REPO_DIR):
        return
    
    gh_config = os.path.expanduser('~/.config/gh/hosts.yml')
    if not os.path.exists(gh_config):
        return
    with open(gh_config) as f:
        content = f.read()
    
    user_m = re.search(r'user:\s*(\S+)', content)
    token_m = re.search(r'oauth_token:\s*(\S+)', content)
    if not user_m or not token_m:
        return
    
    user, token = user_m.group(1), token_m.group(1)
    
    # Update README.md stats
    readme_path = os.path.join(REPO_DIR, 'README.md')
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            text = f.read()
        text = re.sub(r'prompts-\d+.*?-111', f'prompts-{total_count}%2B-111', text)
        text = re.sub(r'<b>\d+.*?\+ real community', f'<b>{total_count:,}+ real community', text)
        text = re.sub(r'\| \*\*Total Prompts\*\* \| \*\*[\d,]+\*\*', f'| **Total Prompts** | **{total_count:,}**', text)
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(text)
    
    # Sync SKILL.md
    skill_src = os.path.expanduser('~/.hermes/skills/ai-automation/seedance-prompts/SKILL.md')
    if os.path.exists(skill_src):
        with open(skill_src, 'r', encoding='utf-8') as f:
            stext = f.read()
        stext = re.sub(r'\*\*\d+\+ real community results\*\*', f'**{total_count}+ real community results**', stext)
        with open(os.path.join(REPO_DIR, 'SKILL.md'), 'w', encoding='utf-8') as f:
            f.write(stext)
    
    # Sync query script
    query_src = os.path.expanduser('~/.hermes/skills/ai-automation/seedance-prompts/scripts/seedance_query.py')
    if os.path.exists(query_src):
        with open(query_src) as f_in, open(os.path.join(REPO_DIR, 'scripts', 'seedance_query.py'), 'w') as f_out:
            f_out.write(f_in.read())
    
    # Sync scraper script
    scraper_src = os.path.expanduser('~/.hermes/skills/ai-automation/seedance-prompts/scripts/seedance_scraper.py')
    if os.path.exists(scraper_src):
        with open(scraper_src) as f_in, open(os.path.join(REPO_DIR, 'scripts', 'seedance_scraper.py'), 'w') as f_out:
            f_out.write(f_in.read())

    # Commit & push
    try:
        subprocess.run(['git', 'add', '-A'], cwd=REPO_DIR, check=True)
        status = subprocess.run(['git', 'status', '--porcelain'], cwd=REPO_DIR, capture_output=True, text=True)
        if status.stdout.strip():
            msg = f"auto: updated database stats (+{new_count} new prompts, total {total_count:,})"
            subprocess.run(['git', 'commit', '-m', msg], cwd=REPO_DIR, check=True)
            push_url = f"https://{user}:{token}@github.com/{user}/seedance-prompts.git"
            res = subprocess.run(['git', 'push', push_url, 'main'], cwd=REPO_DIR, capture_output=True, text=True)
            if res.returncode == 0:
                print(f"Auto-pushed to GitHub: +{new_count} new prompts (total {total_count:,})")
    except Exception as e:
        print(f"Auto-push error: {e}")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'update'
    
    conn = init_db()
    existing = set(r[0] for r in conn.execute('SELECT url FROM prompts').fetchall())
    
    all_urls = collect_card_urls()
    
    if mode == 'update':
        to_fetch = [u for u in all_urls if u not in existing]
        if not to_fetch:
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
    
    total = conn.execute('SELECT count(*) FROM prompts').fetchone()[0]
    
    if success > 0:
        print(f"Seedance DB updated: +{success} new prompts (total: {total})")
        auto_push_github(success, total)
    
    conn.close()


if __name__ == '__main__':
    main()
