---
name: seedance-prompts
version: 1.0.0
description: "Use when writing Seedance 2.0/2.5 video prompts."
tags: [seedance, video, ai-video, prompts, bytedance, dreamina]
author: Raphael
---

# Seedance Prompt Engineering Skill

Write production-ready Seedance 2.0/2.5 video prompts by learning from **1500+ real community results** stored in a local SQLite DB with FTS5 search.

## When to Use

- User wants to generate a Seedance video prompt
- User wants to understand Seedance prompt patterns/structure
- User wants to find similar prompts to a concept
- User asks "how do I prompt Seedance for X?"
- User mentions Seedance, Dreamina, or ByteDance video generation

## Architecture

```
~/.hermes/data/seedance_prompts.db   ← SQLite + FTS5 (1500+ prompts)
scripts/seedance_query.py            ← Smart query: intent → DB → patterns → prompt
scripts/seedance_scraper.py          ← Scraper (cron auto-update daily)
```

## Workflow

### 1. Understand User Intent

Parse what the user wants to create:
- **Subject**: person, animal, object, scene
- **Style**: cinematic, anime, vlog, commercial, horror, etc.
- **Action**: what happens in the video
- **Mood**: tone, atmosphere
- **Technical**: duration, aspect ratio, camera work

### 2. Query the DB

Run the query script to find relevant prompts:

```bash
python3 ~/.hermes/skills/ai-automation/seedance-prompts/scripts/seedance_query.py "user's description"
```

This returns:
- Top 5 matching prompts (FTS5 ranked)
- **Pattern analysis**: common structures, word counts, camera directions
- **Style signals**: what techniques top prompts use

### 3. Analyze Patterns from Results

From the matching prompts, extract:

| Element | Look For |
|---------|----------|
| **Opening** | How do top prompts start? (subject intro, scene setting, camera direction) |
| **Structure** | Single paragraph vs. sectioned (Subject/Setting/Action/Camera) |
| **Detail level** | Word count, specificity of descriptions |
| **Camera language** | Pan, dolly, tracking, handheld, crane, drone, POV |
| **Temporal cues** | "slow motion", "time-lapse", "continuous shot", beat timing |
| **Style markers** | Film stock references, color grading terms, era aesthetics |
| **Ending** | How prompts close (final beat, camera pull, freeze) |

### 4. Write & Optimize the Prompt

Apply top benchmark patterns from the DB data:

#### Master Cinematic Multi-Shot Structure (Recommended Format)
When writing complex multi-shot, narrative, or physical action video prompts, organize the prompt into clear explicit sections:
1. **SCENE CONTEXT**: Short narrative high-level summary.
2. **ACTIVE REFERENCES**: Precise `<<<image_N>>>` tags mapping image roles (identity, prop, environment).
3. **CHARACTER ANCHOR**: Detailed physical specs, outfit, armor lock, skin texture, and current battle-worn state.
4. **FIRST FRAME AND SPATIAL BLOCKING**: First frame composition, initial action, and ground coverage.
5. **FORMAT MODE**: Shot transition type (e.g. HARD CUT, single take).
6. **OPTICS**: Exact FOV (e.g. 84° wide-angle lens lock).
7. **CAMERA — SHOT A / SHOT B**: Detailed continuous camera trajectory and tracking behavior.
8. **ACTION TIMING — SHOT A / SHOT B**: Exact timestamp breakdowns (0:00-0:02, 0:02-0:03, etc.).
9. **PHYSICS & COLLISION**: Dynamic mass, weight transfer, and real-time plant/environment collision rules.
10. **LIGHTING**: Color temperature (e.g. ~6500K), mood, reflection quality.
11. **AUDIO (BINAURAL 3D ASMR)**: Micro-acoustic details (footsteps, armor friction, respiration, impact sounds).
12. **POSITIVE & NEGATIVE CONSTRAINTS**: Strict exclusions (e.g., no dirt path, no pre-flattened vegetation).

#### 5 Elite Optimization Techniques
1. **Structured Timestamp Protocol (`0-5s:`, `5-10s:`, `10-15s:`)**
   - Seedance 2.5 excels at multi-beat timing when explicitly segmented by timestamps.
2. **Anchor Lock Syntax (`@1`, `@2`, `[Global Config]`, `<<<image_N>>>`)**
   - Lock character face (`@1`) and clothing/assets (`@2`) across shots for character consistency.
   - For image references, use triple angle brackets `<<<image_1>>>`, `<<<image_2>>>`, `<<<image_3>>>` to reference uploaded input images directly.
3. **Temporal Vegetation Lock & Real-Time Collision**
   - Explicitly instruct that 100% of vegetation/environment stays upright/pristine until the exact millisecond of physical contact to avoid AI pre-flattened path errors.
4. **Physical Texture & Friction Anchors**
   - Always specify 3 physical elements: **contact points** (footsteps, grip), **weight/friction** (gravity, momentum, fabric inertia), and **lighting direction** (single dominant light source).
5. **Prompt Evaluation & Scoring**
   - Run `--score` to score a prompt from 0-100 against top DB benchmark criteria before delivering:
     ```bash
     python3 ~/.hermes/skills/ai-automation/seedance-prompts/scripts/seedance_query.py --score "your prompt text here"
     ```

**Seedance 2.5 Best Practices** (from community data):
1. **Be specific about subject appearance** — clothing, hair, skin, accessories
2. **One continuous action** — Seedance excels at single unbroken shots
3. **Camera movement as narrative** — describe the camera journey, not just what's shown
4. **Temporal control** — "slow motion", "real-time", "time-lapse" are well-understood
5. **Style anchors** — reference real film/camera aesthetics ("MiniDV", "35mm", "iPhone footage")
6. **Physical realism cues** — mention contact points, weight, fabric physics
7. **Lighting direction** — one dominant light, describe contrast and palette
8. **No emoji, no hashtags** — pure descriptive text only
9. **Optimal length**:
   - Seedance 2.0: 30-300 words (median ~109)
   - Seedance 2.5 text-to-video: 100-500 words (median ~342)  
   - Seedance 2.5 image-to-video: 200-900 words (median ~399)
10. **End with a beat** — describe the final frame/moment

**Workflow Modes:**
- `Text to video` — most common (1326 prompts). Pure text, no reference needed.
- `Image to video` — provide reference image + motion prompt (97 prompts).
- `Reference to video` — character/style reference + scene description (74 prompts).
- `Video editing` — edit/extend existing video (3 prompts).

### 5. Output Format

Always output:
```markdown
**Model:** Seedance 2.5
**Workflow:** Text to video
**Duration:** [if applicable]
**Aspect Ratio:** [if applicable]

---

[THE PROMPT TEXT]

---

**Pattern source:** Based on [N] similar prompts from DB
**Key patterns applied:** [list 2-3 specific techniques borrowed]
```

## DB Schema

```sql
prompts (
  url TEXT PRIMARY KEY,
  title TEXT,
  model TEXT,            -- "Seedance 2.0" or "Seedance 2.5"
  workflow TEXT,          -- "Text to video", "Image to video", "Reference to video"
  original_prompt TEXT,   -- The actual prompt text
  description TEXT,
  categories TEXT,        -- JSON array: ["Action & Fight Scenes", "Cinematic & Film"]
  settings TEXT,          -- JSON: {duration, resolution, aspect_ratio, ...}
  word_count INTEGER,
  char_count INTEGER
)
-- FTS5 index on: title, original_prompt, description, categories
```

## Categories (with counts)

| Category | Count |
|----------|-------|
| Action & Fight Scenes | 1219 |
| Commercial & Product | 771 |
| Cinematic & Film | 603 |
| Anime & Manga | 547 |
| Music & Dance | 507 |
| Romance & Drama | 440 |
| Nature & Animals | 366 |
| Dark Fantasy & Horror | 214 |
| Sci-Fi & Cyberpunk | 203 |
| Tutorials & Tips | 115 |
| Historical & Cultural | 104 |
| Comedy & Satire | 98 |

## Auto-Update

Cron job runs daily to scrape new prompts:
```bash
python3 ~/.hermes/skills/ai-automation/seedance-prompts/scripts/seedance_scraper.py update
```

## Pitfalls

1. **Don't copy prompts verbatim** — use them as pattern references, adapt to user's concept
2. **Long ≠ better** — Seedance 2.0 prefers concise; 2.5 can handle detail but still needs focus
3. **Camera + action must be physically consistent** — don't describe impossible camera paths
4. **Reference images require separate handling** — prompt structure differs for img2vid
5. **Community results ≠ guaranteed** — results vary by seed, model version, and platform state
