#!/usr/bin/env python3
"""
Smart Seedance prompt query & evaluator — searches DB, analyzes patterns, scores prompts.

Usage:
  python3 seedance_query.py "cinematic night market scene"
  python3 seedance_query.py --score "A young woman walking in Tokyo in slow motion..."
  python3 seedance_query.py --category "Anime" --workflow "Text to video" --limit 10
  python3 seedance_query.py --stats
  python3 seedance_query.py --random 5
"""

import sqlite3, json, sys, os, re, argparse
from collections import Counter

DB_PATH = os.path.expanduser('~/.hermes/data/seedance_prompts.db')


def get_conn():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found at {DB_PATH}")
        print("Run seedance_scraper.py first to populate the database.")
        sys.exit(1)
    return sqlite3.connect(DB_PATH)


def search_prompts(query, limit=5, model=None, workflow=None, category=None):
    """FTS5 search with optional filters."""
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    
    # Build FTS query — use OR for broader recall, quoted phrases stay exact
    words = query.split()
    if '"' not in query and len(words) > 1:
        fts_query = ' OR '.join(words)
    else:
        fts_query = query
    
    # Base query joining FTS
    sql = '''
        SELECT p.*, rank
        FROM prompts p
        JOIN prompts_fts fts ON p.rowid = fts.rowid
        WHERE prompts_fts MATCH ?
    '''
    params = [fts_query]
    
    if model:
        sql += ' AND p.model LIKE ?'
        params.append(f'%{model}%')
    if workflow:
        sql += ' AND p.workflow LIKE ?'
        params.append(f'%{workflow}%')
    if category:
        sql += ' AND p.categories LIKE ?'
        params.append(f'%{category}%')
    
    sql += ' ORDER BY rank LIMIT ?'
    params.append(limit)
    
    try:
        rows = conn.execute(sql, params).fetchall()
    except Exception:
        sql = 'SELECT p.*, 0 as rank FROM prompts p WHERE p.original_prompt LIKE ? OR p.title LIKE ? OR p.description LIKE ?'
        like = f'%{query}%'
        params = [like, like, like]
        if model:
            sql += ' AND p.model LIKE ?'
            params.append(f'%{model}%')
        if workflow:
            sql += ' AND p.workflow LIKE ?'
            params.append(f'%{workflow}%')
        sql += f' LIMIT {limit}'
        rows = conn.execute(sql, params).fetchall()
    
    conn.close()
    return [dict(r) for r in rows]


def analyze_patterns(prompts):
    """Extract structural patterns from a set of prompts."""
    if not prompts:
        return {}
    
    analysis = {
        'count': len(prompts),
        'avg_words': sum(p['word_count'] for p in prompts) // len(prompts),
        'word_range': (min(p['word_count'] for p in prompts), max(p['word_count'] for p in prompts)),
        'models': dict(Counter(p['model'] for p in prompts)),
        'workflows': dict(Counter(p['workflow'] for p in prompts)),
    }
    
    all_cats = []
    for p in prompts:
        try:
            all_cats.extend(json.loads(p.get('categories', '[]')))
        except:
            pass
    analysis['top_categories'] = dict(Counter(all_cats).most_common(5))
    
    camera_terms = ['pan', 'tilt', 'dolly', 'tracking', 'handheld', 'crane', 'drone', 
                    'POV', 'first-person', 'close-up', 'wide shot', 'medium shot',
                    'slow motion', 'time-lapse', 'continuous shot', 'unbroken', '一镜到底', '斯坦尼康']
    
    camera_usage = Counter()
    for p in prompts:
        text = (p.get('original_prompt', '') or '').lower()
        for term in camera_terms:
            if term.lower() in text:
                camera_usage[term] += 1
    analysis['camera_techniques'] = dict(camera_usage.most_common(10))
    
    style_terms = ['cinematic', 'realistic', 'anime', 'vlog', '35mm', 'film grain',
                   'MiniDV', 'iPhone', 'DSLR', 'anamorphic', 'bokeh', 'golden hour',
                   'neon', 'noir', 'vintage', 'retro', '4K', 'photorealistic',
                   'cell-shaded', '3D render', 'watercolor', 'oil painting']
    
    style_usage = Counter()
    for p in prompts:
        text = (p.get('original_prompt', '') or '').lower()
        for term in style_terms:
            if term.lower() in text:
                style_usage[term] += 1
    analysis['style_markers'] = dict(style_usage.most_common(10))
    
    openings = []
    for p in prompts:
        text = (p.get('original_prompt', '') or '').strip()
        if text:
            first_words = ' '.join(text.split()[:10])
            openings.append(first_words)
    analysis['opening_samples'] = openings[:5]
    
    structured = 0
    paragraph = 0
    for p in prompts:
        text = (p.get('original_prompt', '') or '')
        if any(marker in text for marker in ['Main Subject:', 'Location:', 'Camera:', 'Action:', 'Setting:', '0-5s', '@1']):
            structured += 1
        else:
            paragraph += 1
    analysis['structure'] = {'sectioned': structured, 'paragraph': paragraph}
    
    return analysis


def score_prompt(text):
    """
    Evaluates a Seedance prompt against top 10% DB benchmark criteria (0-100 score).
    """
    if not text:
        return {"score": 0, "breakdown": {}, "feedback": ["Empty prompt text."]}
    
    # Read text from file if argument is a valid file path
    if os.path.isfile(text):
        with open(text, 'r', encoding='utf-8') as f:
            text = f.read()

    words = len(text.split())
    chars = len(text)
    
    breakdown = {}
    feedback = []
    
    # 1. Word Count & Length Adequacy (15 pts)
    if words >= 150 and words <= 550:
        breakdown['length'] = 15
    elif words >= 80 and words < 150:
        breakdown['length'] = 10
        feedback.append("Consider expanding details (optimal Seedance 2.5 length is 150–500 words).")
    elif words > 550 and words <= 900:
        breakdown['length'] = 12
    elif words > 900:
        breakdown['length'] = 8
        feedback.append("Prompt is very long (>900 words). Seedance may ignore trailing instructions.")
    else:
        breakdown['length'] = 5
        feedback.append("Prompt is too brief (<80 words). Add physical appearance, camera, and lighting specifics.")
        
    # 2. Subject & Texture Detail (20 pts)
    sub_score = 0
    subject_kw = ['wearing', 'dress', 'shirt', 'jacket', 'hair', 'skin', 'eyes', 'facial', 'texture', 'fabric', 'color', 'age', 'apparel', 'outfit']
    matches_sub = sum(1 for kw in subject_kw if kw in text.lower())
    sub_score = min(20, matches_sub * 4)
    breakdown['subject_detail'] = sub_score
    if sub_score < 12:
        feedback.append("Add detailed subject descriptors (clothing materials, hair style, skin/surface texture).")
        
    # 3. Camera Directives & Framing (20 pts)
    cam_score = 0
    cam_kw = ['pan', 'tilt', 'dolly', 'tracking', 'handheld', 'steadicam', 'crane', 'drone', 'pov', 'close-up', 'wide shot', 'medium shot', 'orbit', 'zoom', 'angle', '镜头', '一镜到底', '拉近', '推镜']
    matches_cam = sum(1 for kw in cam_kw if kw in text.lower())
    cam_score = min(20, matches_cam * 5)
    breakdown['camera_directives'] = cam_score
    if cam_score < 10:
        feedback.append("Specify explicit camera movement (e.g. 'handheld tracking shot', 'slow push in', 'low-angle orbit').")

    # 4. Physical Realism & Friction Anchors (15 pts)
    phys_score = 0
    phys_kw = ['light', 'lighting', 'shadow', 'reflection', 'sunlight', 'neon', 'glow', 'contrast', 'contact', 'footstep', 'dust', 'gravity', 'weight', 'wind', 'reflection', 'ground', 'moisture', 'smoke']
    matches_phys = sum(1 for kw in phys_kw if kw in text.lower())
    phys_score = min(15, matches_phys * 3)
    breakdown['physical_anchors'] = phys_score
    if phys_score < 9:
        feedback.append("Include physical anchors (lighting direction, contact points, reflection, gravity/wind physics).")

    # 5. Timeline / Beat Control (15 pts)
    time_score = 0
    has_timestamps = bool(re.search(r'\b\d+[-–]\d+s\b', text) or re.search(r'Scene \d+|Beat \d+|Phase \d+', text, re.I))
    has_sections = bool(re.search(r'\b(Subject|Location|Camera|Setting|Action|Style):', text, re.I))
    if has_timestamps:
        time_score = 15
    elif has_sections:
        time_score = 12
    elif 'slow motion' in text.lower() or 'real-time' in text.lower() or 'unbroken' in text.lower():
        time_score = 8
    else:
        time_score = 3
        feedback.append("Use structured timestamp blocks (e.g. '0-5s:', '5-10s:') or explicit beat sections.")
        
    breakdown['beat_control'] = time_score

    # 6. Advanced Anchors & Technical Precision (15 pts)
    adv_score = 0
    has_anchors = bool(re.search(r'@\d+', text)) # Anchor tags @1, @2
    has_chinese_terms = bool(re.search(r'[\u4e00-\u9fff]', text))
    has_quality_markers = any(q in text.lower() for q in ['cinematic', '35mm', 'minidv', 'photorealistic', 'shallow depth of field', 'grain', 'bokeh', '16:9', '4k'])
    
    if has_anchors:
        adv_score += 5
    if has_chinese_terms:
        adv_score += 5
    if has_quality_markers:
        adv_score += 5
    
    adv_score = min(15, adv_score)
    breakdown['technical_precision'] = adv_score
    if adv_score < 10:
        feedback.append("Consider adding anchor tags (@1, @2 for character/costume lock) or film style markers (35mm, bokeh).")

    total_score = sum(breakdown.values())
    
    return {
        "score": total_score,
        "word_count": words,
        "char_count": chars,
        "breakdown": breakdown,
        "feedback": feedback if feedback else ["Excellent prompt! Meets high-benchmark Seedance 2.5 standards."]
    }


def format_results(prompts, analysis, query):
    """Format results for agent consumption."""
    output = []
    output.append(f"## Seedance Prompt Search: \"{query}\"")
    output.append(f"Found {analysis['count']} matching prompts\n")
    
    output.append("### Pattern Analysis")
    output.append(f"- **Word count:** avg {analysis['avg_words']} (range {analysis['word_range'][0]}-{analysis['word_range'][1]})")
    output.append(f"- **Models:** {analysis['models']}")
    output.append(f"- **Workflows:** {analysis['workflows']}")
    output.append(f"- **Structure:** {analysis['structure']['sectioned']} sectioned, {analysis['structure']['paragraph']} paragraph-style")
    
    if analysis.get('camera_techniques'):
        techniques = ', '.join(f"{k} ({v})" for k, v in analysis['camera_techniques'].items())
        output.append(f"- **Camera techniques used:** {techniques}")
    
    if analysis.get('style_markers'):
        styles = ', '.join(f"{k} ({v})" for k, v in analysis['style_markers'].items())
        output.append(f"- **Style markers:** {styles}")
    
    if analysis.get('top_categories'):
        cats = ', '.join(f"{k} ({v})" for k, v in analysis['top_categories'].items())
        output.append(f"- **Categories:** {cats}")
    
    if analysis.get('opening_samples'):
        output.append("\n### Opening Patterns")
        for i, opening in enumerate(analysis['opening_samples'], 1):
            output.append(f"  {i}. \"{opening}...\"")
    
    output.append("\n### Matching Prompts")
    for i, p in enumerate(prompts, 1):
        output.append(f"\n---\n#### [{i}] {p['title']} ({p['model']}, {p['workflow']})")
        output.append(f"**Words:** {p['word_count']} | **Categories:** {p.get('categories', '[]')}")
        
        prompt_text = p.get('original_prompt', '')
        if len(prompt_text) > 1500:
            output.append(f"\n```\n{prompt_text[:1500]}...\n[truncated — {len(prompt_text)} chars total]\n```")
        else:
            output.append(f"\n```\n{prompt_text}\n```")
    
    return '\n'.join(output)


def get_stats():
    """DB statistics."""
    conn = get_conn()
    
    total = conn.execute('SELECT count(*) FROM prompts').fetchone()[0]
    models = conn.execute('SELECT model, count(*), avg(word_count), max(word_count) FROM prompts GROUP BY model').fetchall()
    workflows = conn.execute('SELECT workflow, count(*) FROM prompts GROUP BY workflow').fetchall()
    
    all_cats = []
    for row in conn.execute('SELECT categories FROM prompts'):
        try:
            all_cats.extend(json.loads(row[0]))
        except:
            pass
    cat_counts = Counter(all_cats).most_common(20)
    
    wc_dist = conn.execute('''
        SELECT 
            CASE 
                WHEN word_count < 50 THEN '< 50'
                WHEN word_count < 100 THEN '50-99'
                WHEN word_count < 200 THEN '100-199'
                WHEN word_count < 300 THEN '200-299'
                WHEN word_count < 500 THEN '300-499'
                ELSE '500+'
            END as bracket,
            count(*)
        FROM prompts GROUP BY bracket ORDER BY min(word_count)
    ''').fetchall()
    
    conn.close()
    
    print(f"## Seedance Prompts DB Stats")
    print(f"\nTotal prompts: {total}")
    print(f"\n### Models:")
    for model, count, avg_wc, max_wc in models:
        print(f"  {model}: {count} prompts (avg {avg_wc:.0f} words, max {max_wc})")
    print(f"\n### Workflows:")
    for wf, count in workflows:
        print(f"  {wf}: {count}")
    print(f"\n### Word Count Distribution:")
    for bracket, count in wc_dist:
        bar = '#' * (count // 3)
        print(f"  {bracket:>10}: {count:>4} {bar}")
    print(f"\n### Top Categories:")
    for cat, count in cat_counts:
        print(f"  {cat}: {count}")


def get_random(n=5):
    """Get N random prompts."""
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute('SELECT * FROM prompts ORDER BY RANDOM() LIMIT ?', (n,)).fetchall()
    conn.close()
    prompts = [dict(r) for r in rows]
    analysis = analyze_patterns(prompts)
    print(format_results(prompts, analysis, "random sample"))


def main():
    parser = argparse.ArgumentParser(description='Seedance prompt DB query & evaluator')
    parser.add_argument('query', nargs='?', help='Search query (natural language)')
    parser.add_argument('--category', '-c', help='Filter by category')
    parser.add_argument('--workflow', '-w', help='Filter by workflow (text/image/reference)')
    parser.add_argument('--model', '-m', help='Filter by model (2.0/2.5)')
    parser.add_argument('--limit', '-l', type=int, default=5, help='Number of results')
    parser.add_argument('--score', '-s', help='Evaluate and score a prompt text or file path')
    parser.add_argument('--stats', action='store_true', help='Show DB statistics')
    parser.add_argument('--random', type=int, metavar='N', help='Get N random prompts')
    
    args = parser.parse_args()
    
    if args.score:
        result = score_prompt(args.score)
        print(f"## Seedance Prompt Evaluation Score: {result['score']}/100")
        print(f"Word count: {result['word_count']} words | Character count: {result['char_count']} chars\n")
        print("### Score Breakdown:")
        for k, v in result['breakdown'].items():
            print(f"  - {k}: {v} pts")
        print("\n### Feedback & Optimization Suggestions:")
        for fb in result['feedback']:
            print(f"  - {fb}")
        return

    if args.stats:
        get_stats()
        return
    
    if args.random:
        get_random(args.random)
        return
    
    if not args.query:
        parser.print_help()
        return
    
    prompts = search_prompts(
        args.query, 
        limit=args.limit,
        model=args.model,
        workflow=args.workflow,
        category=args.category
    )
    
    if not prompts:
        print(f"No results for \"{args.query}\". Try broader terms.")
        conn = get_conn()
        all_cats = []
        for row in conn.execute('SELECT categories FROM prompts'):
            try:
                all_cats.extend(json.loads(row[0]))
            except:
                pass
        conn.close()
        top = Counter(all_cats).most_common(5)
        print(f"Available categories: {', '.join(c for c,_ in top)}")
        return
    
    analysis = analyze_patterns(prompts)
    print(format_results(prompts, analysis, args.query))


if __name__ == '__main__':
    main()
