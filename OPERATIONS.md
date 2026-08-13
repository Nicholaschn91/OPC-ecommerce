# OPERATIONS.md

# OPC-ecommerce Operations Manual

This document contains operational procedures, runbooks, and maintenance guidelines for the OPC-ecommerce multi-agent listing pipeline.

## ���� �� �� 📋 Table of Contents
- [Daily Operations](#daily-operations)
- [Weekly Maintenance](#weekly-maintenance)
- [Monthly Tasks](#monthly-tasks)
- [Incident Response](#incident-response)
- [Performance Tuning](#performance-tuning)
- [Backup and Recovery](#backup-and-recovery)
- [Scaling Guidelines](#scaling-guidelines)
- [Security Procedures](#security-procedures)
- [Troubleshooting Runbooks](#troubleshooting-runbooks)

## ���� �� �� 📅 Daily Operations

### 1. Pipeline Health Check
Run each morning to ensure all components are functioning:

```bash
# Check Hermes gateway health
curl -s http://127.0.0.1:8642/health

# Check agent registry
python -c "from tools.feishu_bitable import FeishuBitable; f=FeishuBitable(); print('Feishu connected:', f.test_connection())"

# Check database connectivity
python -c "import sqlite3; conn=sqlite3.connect('shared/databases/keyword_database.db'); c=conn.cursor(); c.execute('SELECT COUNT(*) FROM keywords'); print('Keywords:', c.fetchone()[0])"

# Check NVIDIA API status (if used)
curl -s --max-time 5 "https://integrate.api.nvidia.com/v1/models" -H "Authorization: Bearer $NVIDIA_API_KEY" | grep -c '"id"' || echo "NVIDIA API check failed"
```

### 2. Queue Monitoring
Check for stuck SPUs in the pipeline:

```bash
# Check for SPUs stuck in any stage for >1 hour
python tools/sop_orchestrator.py --list-stuck --threshold 3600

# Check Feishu for SPUs without recent updates
python -c "
from tools.feishu_bitable import FeishuBitable
f = FeishuBitable()
# Check Base A for old fetches
# Check Base B for incomplete listings
"
```

### 3. Log Review
Review key logs for errors:

```bash
# Hermes agent logs
tail -n 50 ~/.hermes/logs/hermes.log | grep -i error

# Tool logs (if any)
ls -la tools/*.log 2>/dev/null | head -5

# Process logs
ps aux | grep -E "(sop_orchestrator|process_dual|feishu)" | grep -v grep
```

## ���� �� �� 🗓���� Weekly Maintenance

### 1. Database Maintenance
```bash
# Analyze and vacuum SQLite databases
sqlite3 shared/databases/keyword_database.db "VACUUM; ANALYZE;"
sqlite3 shared/databases/risk_keywords.db "VACUUM; ANALYZE;"

# Check database integrity
sqlite3 shared/databases/keyword_database.db "PRAGMA integrity_check;"
sqlite3 shared/databases/risk_keywords.db "PRAGMA integrity_check;"
```

### 2. Dependency Updates
```bash
# Update Python tools dependencies (if requirements exist)
pip list --outdated  # Review manually before updating

# Check for updates to Hermes Agent
hermes version  # Compare with latest release
```

### 3. Configuration Review
```bash
# Check for drift in config.yaml
git diff config.yaml  # Should be clean unless intentional changes

# Verify environment variables are set correctly
env | grep -E "(HERMES|NVIDIA|OPENROUTER|AGNES|FEISHU)" | sort
```

### 4. Test Suite
Run full test suite to catch regressions:

```bash
python -m pytest tests/ -v --tb=short
```

## ���� �� �� 📆 Monthly Tasks

### 1. Deep Performance Analysis
```bash
# Profile a full pipeline run for a sample SPU
python tools/sop_orchestrator.py --spu <sample_spu> --profile --output profile.out

# Analyze bottlenecks
snakeviz profile.out  # if snakeviz installed
```

### 2. Capacity Planning
Review throughput metrics:
- Average time per SPU through each stage
- Success/failure rates by stage
- Resource utilization (CPU, memory, API calls)

### 3. Documentation Update
- Update this OPERATIONS.md with any new procedures
- Review and update agent SKILL.md files if processes have changed
- Verify that README.md reflects current capabilities

## ���� �� �� 🚨 Incident Response

### 1. Pipeline Stalled (No new completions)
**Symptoms**: No SPUs completing for extended period despite input available

**Response**:
1. Check Hermes gateway: `curl http://127.0.0.1:8642/health`
2. Check for stuck processes: `ps aux | grep python`
3. Check Feishu connectivity: test read/write permissions
4. Check API rate limits: especially NVIDIA 429 errors
5. Look for deadlocks in logs
6. If needed, restart orchestration services

### 2. High Failure Rate in Specific Stage
**Symptoms**: >30% failure rate in a particular agent stage

**Response**:
1. Check recent changes to that agent's SKILL.md or tools
2. Verify input data format hasn't changed
3. Check external API status (if stage calls external services)
4. Review logs for specific error patterns
5. Consider rolling back recent changes if correlated

### 3. Compliance False Positives/Negatives
**Symptoms**: Legitimate listings blocked or prohibited listings passing

**Response**:
1. Check compliance_local.py for recent changes
2. Verify keyword databases are current
3. Review L2 business rules for edge cases
4. Adjust whitelists/blacklists as needed
5. Retrain/test L3 models if applicable

### 4. Feishu API Errors
**Symptoms**: Permission errors, rate limits, or connection failures

**Response**:
1. Check Feishu app credentials in environment
2. Verify IP allowlists if configured
3. Check rate limit status (Feishu has quotas)
4. Test with minimal API calls to isolate issue
5. Consider refreshing access tokens if using OAuth

## ���� �� �� ⚙������️ Performance Tuning

### 1. NVIDIA API Optimization
If experiencing 429 errors:
- Reduce prompt length for SEO/Visual stages
- Consider using agnes-cn for non-critical tasks
- Implement exponential backoff in tools
- Cache frequent requests where appropriate
- Stagger batch jobs to avoid thundering herd

### 2. Database Performance
- Ensure SQLite databases are on fast storage (SSD)
- Consider WAL mode for better concurrent access:
  ```sql
  PRAGMA journal_mode=WAL;
  ```
- Monitor database size and archive old data if needed

### 3. Hermes Configuration
- Adjust `max_turns` in config.yaml based on task complexity
- Tune `reasoning_effort` (low/medium/high) for cost/performance balance
- Enable/disable `checkpoints` based on fault tolerance needs
- Consider context compression settings for long conversations

### 4. Batch Processing
For tools like batch_compliance.py:
- Tune `--delay` parameter to respect API rate limits
- Consider parallel processing where safe (but watch for database locks)
- Use checkpoints to allow resume from failure points
- Monitor memory usage for large batches

## ���� �� �� 💾 Backup and Recovery

### 1. Critical Data to Backup
- `shared/databases/keyword_database.db` (primary keyword source)
- `shared/databases/risk_keywords.db` (risk word source)
- Feishu Bitable bases (Base A, Base B) - via Feishu export
- Hermes agent configurations and skills
- Custom agent definitions and prompts

### 2. Backup Procedures
#### Keyword Databases (Daily)
```bash
# Create timestamped backup
cp shared/databases/keyword_database.db shared/databases/backups/keyword_database_$(date +%Y%m%d_%H%M%S).db
cp shared/databases/risk_keywords.db shared/databases/backups/risk_keywords_$(date +%Y%m%d_%H%M%S).db

# Optional: compress backups
gzip shared/databases/backups/*.db
```

#### Feishu Bitable (Weekly)
Use Feishu's built-in export functionality to export:
- Base A (raw inputs)
- Base B (processed listings)
- Any other custom bases

#### Configuration and Code (On change or weekly)
```bash
# Create git bundle or archive
git bundle create backup_OPC_ecommerce_$(date +%Y%m%d).git master
# Or create tar.gz of important directories
tar -czf config_backup_$(date +%Y%m%d).tar.gz \
  config/ agents/*/SKILL.md docs/SOP/ .hermes.md
```

### 3. Recovery Procedures
#### From Keyword Database Backup
1. Stop any processes writing to the databases
2. Copy backup back to live location:
   ```bash
   cp shared/databases/backups/keyword_database_YYYYMMDD_HHMMSS.db shared/databases/keyword_database.db
   cp shared/databases/backups/risk_keywords_YYYYMMDD_HHMMSS.db shared/databases/risk_keywords.db
   ```
3. Verify integrity with `PRAGMA integrity_check;`
4. Resume processes

#### From Feishu Backup
1. Use Feishu import functionality to restore bases
2. Verify critical fields are present
3. Check that agent expectations match restored schema

#### From Git Backup
1. Clone from bundle or extract tar.gz
2. Verify configuration matches expected state
3. Run health checks before resuming pipeline

## ���� �� �� 📈 Scaling Guidelines

### 1. Horizontal Scaling (More SPUs)
The pipeline is designed to process SPUs independently, so horizontal scaling is straightforward:
- Run multiple instances of `sop_orchestrator.py` with different SPU ranges
- Ensure each instance has its own working directory or uses file locking
- Monitor shared resource usage (databases, API rate limits)
- Consider using a queue system (like Redis) for SPU distribution if needed

### 2. Vertical Scaling (More Throughput per SPU)
To increase throughput for individual SPUs:
- Optimize slowest stages first (typically Visual and SEO due to LLM calls)
- Consider using faster/cheaper models for initial drafts
- Implement result caching for deterministic transformations
- Increase Hermes `max_turns` only if needed for complex reasoning

### 3. Resource Bottlenecks to Watch
| Resource | Symptom | Solution |
|----------|---------|----------|
| NVIDIA API | 429 errors, timeouts | Reduce prompt length, use caching, stagger calls |
| Agnes API | Authentication errors, slow response | Check keys, consider caching, use alternative models |
| Feishu API | Rate limits, permission errors | Optimize read/write patterns, batch operations |
| SQLite DB | Locked database errors | Implement proper connection pooling, WAL mode |
| Disk Space | "No space left on device" | Clean logs, archive old data, compress backups |
| Memory | OOM kills, slow performance | Increase swap, optimize data structures, process in batches |

## ���� �� �� 🔐 Security Procedures

### 1. API Key Management
- Never commit API keys to git (enforced by .gitignore)
- Use environment variables or secure vaults
- Rotate keys periodically (especially for paid services)
- Review which services actually need which keys

### 2. Access Control
- Limit Hermes agent permissions to only what's needed
- Use least privilege principle for Feishu app tokens
- Review github token permissions if used for automation
- Consider using deploy keys instead of personal tokens for git

### 3. Data Protection
- Feishu contains raw product data and potentially sensitive information
- Ensure backups are encrypted or stored securely
- Consider pseudonymization for particularly sensitive fields
- Review data retention policies for different data types

### 4. Network Security
- The system relies on external APIs (Agnes, NVIDIA, eBay, Feishu)
- Ensure outbound connections are allowed as needed
- Consider using a proxy or gateway for external API calls (already done for Hermes 8642)
- Monitor for data exfiltration patterns in logs

## ���� �� �� 🔧 Troubleshooting Runbooks

### Runbook 1: "My SPUs are not moving past Router"
**Steps**:
1. Check if `CRITICAL_STOP` gate is waiting for human confirmation
2. Look at Router logs for errors in strategy generation
3. Verify keyword databases are accessible and not corrupted
4. Check that Base A has sufficient input data for the SPU
5. Test Router in isolation with known good input
6. Check for NVIDIA rate limiting if using for Router

### Runbook 2: "SEO stage is timing out"
**Steps**:
1. Check NVIDIA API status and rate limits
2. Reduce complexity of SEO prompts if possible
3. Try switching to agnes-cn if enabled and appropriate
4. Check that SPU_CONTEXT is properly formed from Router output
5. Test SEO agent with a simple, known input
6. Consider breaking large prompts into smaller chunks

### Runbook 3: "Compliance is blocking everything"
**Steps**:
1. Check if L1 keyword lists are too broad (false positives)
2. Verify that legitimate context whitelists are working
3. Check L2 business rules for overly restrictive conditions
4. Verify that L3 LLM is not malfunctioning (if used)
5. Test compliance_local.py directly with known good/bad examples
6. Review recent changes to keyword databases

### Runbook 4: "Feishu writes are failing"
**Steps**:
1. Verify FEISHU_APP_ID and FEISHU_APP_SECRET are correct
2. Check that the app has granted permissions to the specific bases
3. Look for permission errors in Feishu API responses
4. Verify that the target fields exist and are writable
5. Check rate limit headers in Feishu responses
6. Test read/write cycle with a dummy SPU

### Runbook 5: "Hermes agent is not responding"
**Steps**:
1. Check Hermes gateway health: `curl http://127.0.0.1:8642/health`
2. Review Hermes logs for errors or deadlocks
3. Check memory and CPU usage on the host machine
4. Verify that the Hermes process is not stuck in a loop
5. Consider restarting the Hermes agent service
6. Check for upstream service issues (model provider, etc.)

## ���� �� �� 📞 Contacts and Escalation

### Primary Contacts
- **SOP Questions / Agent Definitions**: Hermes (SOP authority)
- **Tool Questions / Script Issues**: office-workbuddy (tool authority)
- **Database Issues**: office-workbuddy (owns keyword databases)
- **Infrastructure / DevOps**: [To be defined based on org structure]

### Escalation Path
1. First responder: Person on-call for the specific domain
2. Domain specialist: Hermes for SOP, office-workbuddy for tools
3. System architect: For cross-cutting or architectural issues
4. Vendor support: For external API issues (Agnes, NVIDIA, Feishu, etc.)
5. Leadership: For prolonged outages or business impact incidents

---
*Last updated: 2026-08-13*
*Version: 1.0*
*Next review: 2026-09-13*