<p align="center">
  <h1 align="center">🎬 Seedance Prompts</h1>
</p>

<p align="center">
  <b>ByteDance Seedance 2.0 & 2.5 Prompt Engineering & Benchmark Toolkit</b><br />
  SQLite + FTS5 full-text search engine over <b>7,350+ real community video production cards</b>.
</p>

<p align="center">
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square" /></a>
  <a href="#features"><img alt="Prompts Indexed" src="https://img.shields.io/badge/prompts-7350%2B-111?style=flat-square" /></a>
  <a href="#quick-start"><img alt="Models Supported" src="https://img.shields.io/badge/seedance-2.0%20%7C%202.5-purple?style=flat-square" /></a>
  <a href="#quick-start"><img alt="Python" src="https://img.shields.io/badge/python-3.8%2B-green?style=flat-square" /></a>
</p>

---

## 🌟 Overview

`seedance-prompts` is an open-source prompt engineering toolkit designed for **ByteDance Seedance 2.0 & Seedance 2.5** (accessible via Dreamina). It indexes over **1,500+ source-linked production cards**, analyzes high-performing prompt patterns, and provides an automated prompt quality evaluation system.

---

## 🚀 Quick Start

### 1. Installation

```bash
git clone https://github.com/ardha27/seedance-prompts.git
cd seedance-prompts
```

### 2. Build Local Database (1,500+ Prompts)

```bash
python3 scripts/seedance_scraper.py full
```

### 3. Search & Analyze Prompts

Search the database with natural language queries to discover top-performing camera movements, word lengths, and category patterns:

```bash
python3 scripts/seedance_query.py "cinematic night market vlog"
```

### 4. Score & Benchmark Your Prompt (0–100)

Evaluate any Seedance prompt against top community benchmark criteria:

```bash
python3 scripts/seedance_query.py --score "A young woman in a teal apron walking through a night street market..."
```

---

## ⚡ Key Features

- **🔍 FTS5 Full-Text Search**: Fast SQLite full-text search across 1,500+ real community prompts.
- **📊 Automatic Pattern Extraction**: Analyzes word counts, camera techniques (handheld, Steadicam, dolly), and style anchors.
- **💯 Prompt Quality Evaluator**: Scores prompts from 0–100 based on 6 criteria (Subject detail, camera directives, physical friction anchors, timestamp timeline control, technical markers, length).
- **⏱️ Timestamp & Anchor Support**: Full support for Seedance 2.5 `0-5s:` timing blocks and `@1`, `@2` character consistency anchors.
- **🔄 Auto-Updater Scraper**: Built-in scraper script with thread-pool concurrency for silent daily DB updates.

---

## 📊 Database Statistics

| Metric | Count / Value |
|--------|---------------|
| **Total Prompts** | **7,350** |
| **Seedance 2.5** | 1,169 (avg 342 words) |
| **Seedance 2.0** | 331 (avg 109 words) |
| **Text-to-Video** | 1,326 |
| **Image-to-Video** | 97 |
| **Reference-to-Video** | 74 |
| **Top Categories** | Action (1219), Commercial (771), Cinematic (603), Anime (547), Music (507) |

---

## 🧠 5 Elite Prompt Optimization Strategies

1. **Structured Timestamp Protocol (`0-5s:`, `5-10s:`, `10-15s:`)**: Divide actions into timeline blocks for exact multi-beat synchronization.
2. **Anchor Lock Syntax (`@1`, `@2`)**: Explicitly tag facial features (`@1`) and outfits (`@2`) to maintain multi-shot character identity.
3. **Bilingual Camera Directives**: Injecting native Chinese camera terms (`一镜到底` = one-take, `斯坦尼康` = Steadicam) boosts motion compliance on Seedance 2.5.
4. **Physical Texture & Friction Anchors**: Specify footstep contact points, fabric inertia, and single-source lighting for maximum photorealism.
5. **Pre-Flight Prompt Scoring**: Use `--score` to verify prompt readiness prior to rendering.

---

## 🤝 Contributing

Contributions are welcome! Please check out [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## 📜 License

Distributed under the [MIT License](LICENSE).
