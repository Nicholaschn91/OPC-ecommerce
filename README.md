# OPC-ecommerce

Cross-border e-commerce multi-agent listing pipeline.

This repository is the **canonical** source for the OPC (OPC: One Product, Complete) e-commerce listing generation system, consisting of 19 specialized agents that transform raw product data into optimized listings for platforms like eBay, Amazon, etc.

## �� 📋 Table of Contents
- [Overview](#overview)
- [Repository Structure](#repository-structure)
- [Division of Labor](#division-of-labor)
- [Getting Started](#getting-started)
- [Running the Pipeline](#running-the-pipeline)
- [Agent Boundaries](#agent-boundaries)
- [Data Flow](#data-flow)
- [Configuration](#configuration)
- [Development Guidelines](#development-guidelines)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## �� 🏗��️ Overview

The OPC-ecommerce system automates the creation of high-quality, compliant product listings for cross-border e-commerce. It follows a strict SOP (Standard Operating Procedure) divided into stages:

1. **Data Collection** (Scraper, Image PostProcessor)
2. **Keyword Grading** (Keyword Grader)
3. **Routing** (Router)
4. **SEO Generation** (SEO Agent)
5. **Visual Generation** (Visual Agent)
6. **Compliance Check** (Dify Compliance / Local Compliance)
7. **Ads Generation** (Ads Agent)
8. **Domain Management** (Product, Marketing, Fulfillment, Reputation Domains)
9. **Asset Management** (Asset Manager)

The system uses Feishu (Lark) Bitable as the central data store for all intermediate and final outputs.

## �� 📂 Repository Structure

```
OPC-ecommerce/
├── agents/                 # Agent definitions (SKILL.md, prompts, configs)
│   ├── 01_Scraper/
│   ├── 02_Keyword_Grader/
│   ├── 03_Router/
│   ├── 04_SEO/
│   ├── 05_Visual/
│   ├── 06_Dify_Compliance/
│   ├── 07_Ads/
│   ├── 08_Customer_Service/
│   ├── 09_Image_PostProcessor/
│   ├── 10_DataAnalyst/
│   ├── 11_Finance/
│   ├── 12_ProductDomain/
│   ├── 13_MarketingDomain/
│   ├── 14_FulfillmentDomain/
│   ├── 15_ReputationDomain/
│   ├── 16_ReviewReputation/
│   ├── 17_CompetitorDefense/
│   ├── 90_AssetManager/
│   ├── eBay/               # Custom eBay agent
│   └── ...                 # Other domain agents
├── config/                 # Configuration files
│   ├── AGENT_BOUNDARIES.md # Agent read/write permission matrix
│   ├── AGENT_REGISTRY.md   # Agent registry and metadata
│   ├── config.yaml         # Hermes agent configuration
│   ├── DIFY_RAG.md         # Dify RAG pipeline configuration
│   ├── QUALITY_BENCHMARKS.md # Quality assessment frameworks
│   └── SCHEMA_SUPPLEMENT.md # Database schema extensions
├── docs/                   # Documentation and SOP details
│   ├── SOP/                # Standard Operating Procedures
│   └── ...                 # Other documentation
├── handoff/                # Handoff documents between agents
├── knowledge-base/         # Domain knowledge and references
├── references/             # Reference materials and templates
├── shared/                 # Shared resources
│   ├── databases/          # SQLite databases: keyword_database.db, risk_keywords.db
│   └── events/             # Event schemas and examples
├── skills/                 # Reusable skills for agents
├── tools/                  # Utility scripts and helper functions
│   ├── compliance_local.py     # Three-layer compliance check (L1/L2/L3)
│   ├── feishu_bitable.py       # Feishu Bitable read/write wrapper
│   ├── sop_orchestrator.py     # SOR (Standard Operating Procedure) orchestrator
│   ├── batch_compliance.py     # Batch compliance checker
│   ├── process_dual.py         # Dual keyword processing with retrier fix
│   └── ...                     # Other utilities
├── tests/                  # Unit and integration tests
├── state/                  # Persistent state (SPU states, etc.)
├── data/                   # Static data files
├── .hermes.md              # Hermes project metadata
�└── README.md               # This file
```

## �� 👥 Division of Labor

As per the merger agreement between Hermes (SOP authority) and office-workbuddy (tool authority):

### Hermes Responsibilities (SOP Authority)
- **SOP Definition and Maintenance**: All SOP documents in `docs/SOP/`
- **Agent Skill Definitions**: `SKILL.md` files in each agent directory
- **Visual Pipeline**: Design and maintenance of the visual generation pipeline
- **Keyword Strategy**: Overall keyword strategy and grading logic (in coordination with WorkBuddy)
- **Governance Documents**: This README, OPERATIONS.md, MIGRATION.md, and AGENT_BOUNDARIES.md
- **System Governance**: All treatment documents (README, OPERATIONS, MIGRATION, AGENT_BOUNDARIES)

### office-workbuddy Responsibilities (Tool Authority)
- **Tool Maintenance**: All scripts in the `tools/` directory
- **Skill Maintenance**: Skills in the `skills/` directory (e.g., hicustom-synthesis, doubao-raw-grabber, glm52-* etc.)
- **Keyword Databases**: Exclusive ownership and maintenance of:
  - `shared/databases/keyword_database.db` (read-only for Hermes agents)
  - `shared/databases/risk_keywords.db` (read-only for Hermes agents)
- **Data Collection**: Ownership of the scraping and data collection tools
- **CLI Tools**: Maintenance of command-line interfaces

### Boundary Rules (Enforced by AGENT_BOUNDARIES.md)
- Hermes **must not** modify:
  - Any file in `tools/`
  - `shared/databases/keyword_database.db`
  - `shared/databases/risk_keywords.db`
- office-workbuddy **must not** modify:
  - Any SOP document in `docs/SOP/`
  - Any agent `SKILL.md` file
  - Governance documents (README.md, OPERATIONS.md, MIGRATION.md, AGENT_BOUNDARIES.md)
  - Agent registry and boundary definitions

## �� 🚀 Getting Started

### Prerequisites
- [Hermes Agent](https://hermes-agent.nousresearch.com) installed and configured
- Access to required APIs (Agnes AI, NVIDIA, eBay, etc.) via environment variables
- Feishu Bitable app configured with appropriate permissions
- Git for version control

### Installation
1. Clone the repository:
   ```bash
   git clone git@github.com:Nicholaschn91/OPC-ecommerce.git
   cd OPC-ecommerce
   ```
2. (Optional) Set up a virtual environment for Python tools:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt  # if exists
   ```
3. Configure environment variables (see `.env.example` or config.yaml for required keys)
4. Ensure Feishu Bitable bases (Base A, Base B) are set up according to the SOP

## �� ⚙��️ Running the Pipeline

### Full Pipeline Execution
The pipeline is orchestrated via the `sop-orchestrator` tool:

```bash
python tools/sop_orchestrator.py --spu <SPU_ID> --full
```

### Stage-by-Stage Execution
You can run individual stages for debugging:

```bash
# Run only the Router stage
python tools/sop_orchestrator.py --spu <SPU_ID> --stage router

# Run SEO stage
python tools/sop_orchestrator.py --spu <SPU_ID> --stage seo

# Run Visual stage
python tools/sop_orchestrator.py --spu <SPU_ID> --stage visual

# Run Compliance check
python tools/sop_orchestrator.py --spu <SPU_ID> --stage compliance
```

### Batch Operations
For processing multiple SPUs:

```bash
# Batch compliance check
python tools/batch_compliance.py --platform amazon --delay 0.2

# Batch SEO generation
# (See seo_gen_run.py for examples)
```

## �� 🔒 Agent Boundaries

See [config/AGENT_BOUNDARIES.md](config/AGENT_BOUNDARIES.md) for the detailed read/write permission matrix for each agent on Feishu Bitable fields.

**Core Principle**: Agents are strictly limited to reading and writing only the fields necessary for their function. Violations are detected, logged, and trigger automatic re-runs or circuit breakers.

## �� 🔄 Data Flow

Data flows through the system in the following sequence (simplified):

```
Feishu Base A (Raw Inputs)
       � ↓
[01_Scraper] → Writes scraped data to Base A
       � ↓
[02_Keyword_Grader] → Reads keyword_database.db, writes graded keywords to Base A
       � ↓
[03_Router] → Reads Base A + keyword data, writes routing strategy to Base B (Product)
       � ↓
[04_SEO] → Reads SPU_CONTEXT, writes initial listing (title, bullets, ST, description) to Base B (Listing)
       � ↓
[05_Visual] → Reads initial listing, writes final listing + visual prompts to Base B
       � ↓
[06_Dify_Compliance] → Scans listing content, writes compliance results to Base B
       � ↓
[07_Ads] → Reads initial listing, writes ad copy to dedicated Ad base
       � ↓
[Domain Agents] → Update domain-specific statuses and dispatch signals
       � ↓
[90_AssetManager] → Final arbiter for all writes to Feishu (reads/writes all bases)
```

*Note: Human confirmation gates exist after Router (CRITICAL_STOP) and after SEO/Visual initial version (HUMAN_CONFIRM).*

## �� ⚙��️ Configuration

Primary configuration is in `config/config.yaml`. Key sections:
- `agent`: Default agent settings (max_turns, personalities, etc.)
- `terminal`: Terminal session settings
- `checkpoints`: Enable/disable checkpointing
- `compression`: Context compression settings
- `display`: UI and language settings
- `models`: List of available models with their environment variable keys

Environment variables for API keys are referenced in `config.yaml` via `key_env` fields. Common keys include:
- `NVIDIA_API_KEY`
- `HERMES_API_KEY` (for the Hermes 8642 gateway proxy)
- `HERMES_CUSTOM_APIHUB_AGNES_AI_COM_API_KEY` (Agnes international)
- `HERMES_AGNES_CN_API_KEY` (Agnes domestic) *Note: currently aliased via APIHUB_AGNES_AI_CN_API_KEY*
- `OPENROUTER_API_KEY`
- `GITHUB_TOKEN` (for git operations)
- `FEISHU_APP_ID`, `FEISHU_APP_SECRET` (for Feishu API)

See `config.yaml` for the full list.

## �� 🛠��️ Development Guidelines

### Making Changes
1. **If you are modifying SOP or agent definitions** (Hermes territory):
   - Edit files in `docs/SOP/`, `agents/*/SKILL.md`, `config/AGENT_BOUNDARIES.md`, or governance documents.
   - **Do not modify** anything in `tools/` or the keyword databases.
2. **If you are modifying tools or skills** (office-workbuddy territory):
   - Edit files in `tools/` or `skills/`.
   - **Do not modify** SOP documents, agent SKILL.md files, or governance documents.
3. **Always respect the division of labor** to avoid merge conflicts and maintain clear ownership.

### Code Style
- Follow existing patterns in the codebase.
- For Python tools: prefer clarity and minimal dependencies (YAGNI principle).
- For agent prompts: be specific, concise, and test with small inputs first.
- Keep changes atomic and well-documented.

### Testing
- Run existing tests with `pytest`:
  ```bash
  python -m pytest tests/ -v
  ```
- Add new tests for new functionality in the `tests/` directory.
- For agent changes, test end-to-end with a known SPU before deploying.

## �� 🐛 Troubleshooting

### Common Issues
| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| `429` errors from NVIDIA API | Rate limiting | Wait or reduce prompt length; consider using agnes-cn for SEO/Visual if enabled |
| Authentication errors with Agnes | Invalid or missing API key | Check environment variables and corresponding `key_env` in config.yaml |
| Feishu API permission errors | Missing or incorrect app credentials | Verify `FEISHU_APP_ID` and `FEISHU_APP_SECRET` |
| Compliance checks failing unexpectedly | Missing L2 fields (title, bullets, etc.) | Ensure SEO/Visual stages have run to produce required fields |
| Database locked errors | Concurrent access to SQLite | Ensure only one process writes to keyword/risk DBs at a time |

### Debugging Tools
- Use `python tools/sop_orchestrator.py --spu <ID> --stage <stage> --debug` for verbose output
- Check Feishu Bitable update logs in the `state/` directory
- Review Hermes agent logs in `~/.hermes/logs/`
- Use the `batch_compliance.py` tool to verify compliance across many SPUs

## �� 📜 License

This project is proprietary software. All rights reserved.

## �� 🙏 Acknowledgments

Thanks to the Hermes Agent platform for providing the agent orchestration framework, and to all contributors to the OPC-ecommerce system.

---
*Last updated: 2026-08-13*