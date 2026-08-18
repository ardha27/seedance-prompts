#!/usr/bin/env python3
"""
Seedance multi-source prompt scraper — fetches community prompts from:
1. bestseedanceprompts.com (1,500+ prompts)
2. seedance2prompts.com (5,700+ prompts)
and stores them in a local SQLite DB with FTS5 search.

Auto-pushes updated stats & scripts to GitHub when new prompts are added.

Usage:
  python3 seedance_scraper.py full    # Scrape all from all sources
  python3 seedance_scraper.py update  # Only fetch new prompts (cron mode)
  python3 seedance_scraper.py seedance2 # Scrape only seedance2prompts.com
  python3 seedance_scraper.py best    # Scrape only bestseedanceprompts.com
"""

import urllib.request, re, json, time, sqlite3, os, sys, subprocess
import html as htmlmod
from concurrent.futures import ThreadPoolExecutor, as_completed

DB_PATH = os.path.expanduser('~/.hermes/data/seedance_prompts.db')
REPO_DIR = '/home/rishua/seedance-prompts'

SOURCE_BEST = 'https://bestseedanceprompts.com'
SOURCE_SEEDANCE2 = 'https://seedance2prompts.com'


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


def fetch_bestseedance_detail(card_url):
    full_url = SOURCE_BEST + card_url if card_url.startswith('/') else card_url
    try:
        req = urllib.request.Request(full_url, headers={
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        })
        resp = urllib.request.urlopen(req, timeout=15)
        raw = resp.read().decode('utf-8')
        
        detail = {'url': card_url}
        
        m = re.search(r'<h[12][^>]*>(.*?)</h[12]>', raw, re.DOTALL)
        if m:
            detail['title'] = htmlmod.unescape(re.sub(r'<[^>]+>', '', m.group(1)).strip())
        
        m = re.search(r'model-badge">(Seedance [^<]+)<', raw)
        detail['model'] = m.group(1).strip() if m else 'Seedance 2.5'
        
        m = re.search(r'workflow-badge">([^<]+)<', raw)
        detail['workflow'] = m.group(1).strip() if m else 'Text to video'
        
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
        else:
            detail['provenance'] = 'bestseedanceprompts.com'
        
        return detail
    except Exception as e:
        return {'url': card_url, 'error': str(e)}


def fetch_seedance2_detail(url):
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        })
        resp = urllib.request.urlopen(req, timeout=15)
        content = resp.read().decode('utf-8')
        
        title = ""
        tm = re.search(r'<h1[^>]*>(.*?)</h1>', content, re.DOTALL)
        if tm:
            title = htmlmod.unescape(re.sub(r'<[^>]+>', '', tm.group(1)).strip())
            
        description = ""
        dm = re.search(r'<meta name="description" content="([^"]+)"', content)
        if dm:
            description = htmlmod.unescape(dm.group(1).strip())
            
        pm = re.search(r'<p[^>]*font-mono[^>]*whitespace-pre-wrap[^>]*>(.*?)</p>', content, re.DOTALL)
        prompt_text = ""
        if pm:
            prompt_text = htmlmod.unescape(re.sub(r'<[^>]+>', '', pm.group(1)).strip())
            
        # Extract tags before footer
        footer_pos = content.find('<footer')
        content_area = content[:footer_pos] if footer_pos != -1 else content
        tag_matches = re.findall(r'<a[^>]*href="/tags/([^"]+)"[^>]*>(.*?)</a>', content_area)
        categories = list(dict.fromkeys(htmlmod.unescape(re.sub(r'<[^>]+>', '', t[1]).strip()) for t in tag_matches if t[1].strip()))
        tag_slugs = [t[0].lower() for t in tag_matches]
        
        # JSON-LD CreativeWork
        creative_work = None
        for j in re.findall(r'<script type="application/ld\+json">(.*?)</script>', content, re.DOTALL):
            try:
                d = json.loads(j)
                if d.get('@type') == 'CreativeWork':
                    creative_work = d
                    break
            except:
                pass
                
        author = ""
        author_url = ""
        video_url = ""
        thumb_url = ""
        date_pub = ""
        lang = "en"
        
        if creative_work:
            if isinstance(creative_work.get('author'), dict):
                author = creative_work['author'].get('name', '')
                author_url = creative_work['author'].get('url', '')
            if isinstance(creative_work.get('video'), dict):
                video_url = creative_work['video'].get('contentUrl', '')
                thumb_url = creative_work['video'].get('thumbnailUrl', '')
            date_pub = creative_work.get('datePublished', '')
            lang = creative_work.get('inLanguage', 'en')
            if not title:
                title = creative_work.get('name', '')
            if not description:
                description = creative_work.get('description', '')
                
        if not author_url:
            am = re.search(r'href="(https://x\.com/[^"]+)"', content)
            if am:
                author_url = am.group(1)
                
        model = "Seedance 2.5"
        if "Seedance 2.0" in content and "Seedance 2.5" not in content:
            model = "Seedance 2.0"
            
        workflow = "Text to video"
        if 'r2v' in tag_slugs or 'reference' in url.lower() or 'r2v' in url.lower() or any('reference' in c.lower() for c in categories):
            workflow = "Reference to video"
        elif 'image-to-video' in tag_slugs or 'i2v' in tag_slugs:
            workflow = "Image to video"
        elif 'one-take' in tag_slugs:
            workflow = "Text to video (One-take)"
            
        settings = {
            'language': lang,
            'date_published': date_pub,
            'video_url': video_url,
            'thumbnail_url': thumb_url,
            'author_name': author,
            'author_url': author_url,
            'tags': tag_slugs
        }
        
        return {
            'url': url,
            'title': title,
            'model': model,
            'workflow': workflow,
            'original_prompt': prompt_text,
            'description': description,
            'categories': categories,
            'settings': settings,
            'provenance': author_url or author or 'seedance2prompts.com',
            'word_count': len(prompt_text.split()),
            'char_count': len(prompt_text)
        }
    except Exception as e:
        return {'url': url, 'error': str(e)}


def collect_bestseedance_urls():
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
        url = SOURCE_BEST + cat_path
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            resp = urllib.request.urlopen(req, timeout=15)
            raw = resp.read().decode('utf-8')
            links = re.findall(r'<h3[^>]*>\s*<a href="(/prompts/[^"]+)">([^<]+)</a>', raw)
            for u, t in links:
                if u not in all_urls:
                    all_urls[u] = ('best', htmlmod.unescape(t))
        except:
            pass
        time.sleep(0.1)
    
    try:
        req = urllib.request.Request(SOURCE_BEST, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=15)
        raw = resp.read().decode('utf-8')
        links = re.findall(r'<h3[^>]*>\s*<a href="(/prompts/[^"]+)">([^<]+)</a>', raw)
        for u, t in links:
            if u not in all_urls:
                all_urls[u] = ('best', htmlmod.unescape(t))
    except:
        pass
    
    return all_urls


def collect_seedance2_urls():
    """Collect all unique English prompt URLs from seedance2prompts.com sitemap."""
    try:
        req = urllib.request.Request(f"{SOURCE_SEEDANCE2}/sitemap.xml", headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_content = resp.read().decode('utf-8')
        locs = re.findall(r'<loc>(.*?)</loc>', xml_content)
        en_prompts = [l for l in locs if '/prompts/' in l and not '/zh/' in l]
        return {u: ('seedance2', u.split('/')[-1]) for u in en_prompts}
    except Exception as e:
        print(f"Error fetching seedance2 sitemap: {e}")
        return {}


def upsert_to_db(conn, detail):
    if not detail or detail.get('error') or not detail.get('original_prompt'):
        return False
    
    prompt = detail.get('original_prompt', '').strip()
    if not prompt:
        return False
        
    title = detail.get('title', '').strip() or 'Untitled Prompt'
    
    conn.execute('''INSERT INTO prompts (url, title, model, workflow, original_prompt, description,
                     categories, settings, provenance, word_count, char_count, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                     ON CONFLICT(url) DO UPDATE SET
                     title=excluded.title, model=excluded.model, workflow=excluded.workflow,
                     original_prompt=excluded.original_prompt, description=excluded.description,
                     categories=excluded.categories, settings=excluded.settings,
                     provenance=excluded.provenance, word_count=excluded.word_count,
                     char_count=excluded.char_count, updated_at=datetime('now')''',
                  (detail['url'], title, detail.get('model', 'Seedance 2.5'),
                   detail.get('workflow', 'Text to video'), prompt, detail.get('description', ''),
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
    
    all_targets = {}
    
    if mode in ('full', 'update', 'best'):
        print("Collecting URLs from bestseedanceprompts.com...")
        best_urls = collect_bestseedance_urls()
        all_targets.update(best_urls)
        print(f"  Found {len(best_urls)} from bestseedanceprompts.com")
        
    if mode in ('full', 'update', 'seedance2'):
        print("Collecting URLs from seedance2prompts.com...")
        s2_urls = collect_seedance2_urls()
        all_targets.update(s2_urls)
        print(f"  Found {len(s2_urls)} from seedance2prompts.com")
        
    if mode == 'update':
        to_fetch = {u: src_info for u, src_info in all_targets.items() if u not in existing}
        print(f"Update mode: {len(to_fetch)} new prompts to fetch out of {len(all_targets)} total targets.")
        if not to_fetch:
            print("Database is up to date.")
            conn.close()
            return
    else:
        to_fetch = all_targets
        print(f"{mode.upper()} mode: fetching {len(to_fetch)} prompts.")
        
    success = 0
    errors = 0
    total_to_fetch = len(to_fetch)
    
    def process_item(item):
        url, (source, info) = item
        if source == 'best':
            return fetch_bestseedance_detail(url)
        else:
            return fetch_seedance2_detail(url)

    print(f"Starting parallel fetch with 35 workers...")
    batch_size = 50
    items = list(to_fetch.items())
    
    with ThreadPoolExecutor(max_workers=35) as executor:
        futures = {executor.submit(process_item, item): item[0] for item in items}
        done_count = 0
        
        for future in as_completed(futures):
            done_count += 1
            detail = future.result()
            if upsert_to_db(conn, detail):
                success += 1
            else:
                errors += 1
                
            if done_count % batch_size == 0 or done_count == total_to_fetch:
                conn.commit()
                pct = (done_count / total_to_fetch) * 100
                print(f"Progress: {done_count}/{total_to_fetch} ({pct:.1f}%) | Success: {success} | Errors: {errors}")
    
    conn.commit()
    total = conn.execute('SELECT count(*) FROM prompts').fetchone()[0]
    print(f"\nScraping complete! Added/updated {success} prompts (Total in DB: {total:,})")
    
    if success > 0:
        auto_push_github(success, total)
        
    conn.close()


if __name__ == '__main__':
    main()
