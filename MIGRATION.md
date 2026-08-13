# MIGRATION.md

# OPC-ecommerce Migration Guide

This document outlines the migration process from the previous dual-repo setup (OPC-ecommerce + multi-agent-sop) to the unified single repository (OPC-ecommerce as canonical).

## ������ ���� ���� �� ���� �� �� 📋 Table of Contents
- [Migration Overview](#migration-overview)
- [Pre-Migration Checklist](#pre-migration-checklist)
- [Migration Steps](#migration-steps)
- [Post-Migration Verification](#post-migration-verification)
- [Rollback Procedure](#rollback-procedure)
- [Known Issues and Limitations](#known-issues-and-limitations)
- [FAQ](#faq)

## ������ ���� ���� �� ���� �� �� 🔄 Migration Overview

### What Changed
- **Before**: Two separate repositories:
  - `OPC-ecommerce`: Contains SOP definitions, agent SKILLs, governance documents
  - `multi-agent-sop`: Contains tools, skills, keyword databases, and helper scripts
- **After**: Single repository (`OPC-ecommerce`) containing:
  - All SOP documents and agent definitions (unchanged)
  - All tools, skills, and keyword databases (merged from multi-agent-sop)
  - Unified governance and operations documentation

### Goals
1. Eliminate repository drift between SOP and tools
2. Ensure SOP and tools evolve together with atomic commits
3. Simplify cloning, setup, and onboarding (one repo instead of two)
4. Maintain clear division of labor despite single repository
5. Preserve all existing functionality and data

### What Did NOT Change
- **SOP Authority**: Hermes still owns all SOP documents (`docs/SOP/`, `agents/*/SKILL.md`, `config/AGENT_BOUNDARIES.md`, governance docs)
- **Tool Authority**: office-workbuddy still owns all tools (`tools/`, `skills/`, keyword databases)
- **Division of Labor**: The inter-team boundaries remain strictly enforced
- **Data Ownership**: Keyword databases remain exclusively maintained by office-workbuddy
- **Agent Definitions**: No changes to agent SKILL.md files or prompts

## ������ ���� ���� � ���� �� �� ✅ Pre-Migration Checklist

### For Hermes (SOP Team)
- [ ] All SOP documents are up-to-date in `docs/SOP/`
- [ ] All agent `SKILL.md` files reflect current prompts and behavior
- [ ] `config/AGENT_BOUNDARIES.md` is accurate and reviewed
- [ ] No uncommitted changes in SOP-related directories
- [ ] Latest SOP version tagged/branched if needed

### For office-workbuddy (Tool Team)
- [ ] All tools in `tools/` are functional and tested
- [ ] All skills in `skills/` are documented and working
- [ ] `keyword_database.db` and `risk_keywords.db` are current and backed up
- [ ] No uncommitted changes in tool-related directories
- [ ] Latest tool versions tagged/branched if needed

### Joint Verification
- [ ] Both teams agree on the division of labor as documented in this README
- [ ] Both teams have reviewed the post-merge repository structure
- [ ] Backup strategy confirmed for critical data (databases, configurations)
- [ ] Rollback procedure understood and tested

## ������ ���� ���� �� ���� �� �� 📦 Migration Steps

The migration was performed by office-workbuddy with Hermes approval. The steps were:

### 1. Preparation (office-workbuddy)
```bash
# Ensure multi-agent-sop is clean and up-to-date
cd /path/to/multi-agent-sop
git status  # Should be clean or have only intentional changes
git pull origin master

# Create backup bundle of multi-agent-sop (for reference)
git bundle create multi-agent-sop-backup.bundle master

# Verify key files exist:
ls tools/ process_dual.py keyword_tool.py ...
ls shared/databases/keyword_database.db shared/databases/risk_keywords.db
```

### 2. Merge Execution (office-workbuddy)
```bash
# Clone OPC-ecommerce as base (if not already have latest)
cd /path/to
git clone git@github.com:Nicholaschn91/OPC-ecommerce.git
cd OPC-ecommerce
git checkout master
git pull origin master

# Add multi-agent-sop as remote
git remote add multi-agent-sop /path/to/multi-agent-sop
git fetch multi-agent-sop

# Merge multi-agent-sop master into OPC-ecommerce master
# Using ours strategy for any conflicts in SOP files (should be none)
git merge -s ours multi-agent-sop/master --no-commit

# Now manually merge the tool directories (since we want their content)
git read-tree --prefix=tools/ -u multi-agent-sop/master:tools/
git read-tree --prefix=skills/ -u multi-agent-sop/master:skills/
git read-tree --prefix=shared/databases/ -u multi-agent-sop/master:shared/databases/
git read-tree --prefix=references/ -u multi-agent-sop/master:references/
git read-tree --prefix=knowledge-base/ -u multi-agent-sop/master:knowledge-base/
git read-tree --prefix=docs/ -u multi-agent-sop/master:docs/  # if any docs to merge
git read-tree --prefix=handoff/ -u multi-agent-sop/master:handoff/
git read-tree --prefix=hooks/ -u multi-agent-sop/master:hooks/
git read-tree --prefix=agents/ -u multi-agent-sop/master:agents/  # if any new agents
# Note: Any conflicts in these directories should be resolved in favor of multi-agent-sop content
# since the decision was to take their tools/skills/databases wholesale

# Commit the merge
git commit -m "Merge multi-agent-sop tools, skills, databases into OPC-ecommerce (canonical repo)"
```

### 3. Cleanup and Finalization
```bash
# Remove the temporary remote
git remote remove multi-agent-sop

# Verify the structure matches expectations
ls -la
ls tools/ | wc -l   # Should have many tools
ls skills/ | wc -l  # Should have many skills
ls shared/databases/  # Should see both .db files

# Push to origin (requires authorization)
git push origin master  # --force-with-lease if needed
```

### 4. Tagging (Optional)
```bash
git tag -a v3.0-merged -m "Post-merge version: SOP v3.0 + tools from multi-agent-sop"
git push origin v3.0-merged
```

## ������ ���� ���� � ���� �� �� ✅ Post-Migration Verification

### 1. Repository Structure
```bash
# Verify all expected directories exist
ls -1d agents/ config/ docs/ handoff/ knowledge-base/ references/ shared/ skills/ tools/ tests/

# Verify SOP files are intact
ls agents/*/SKILL.md | wc -l  # Should be ~19 agents
ls docs/SOP/ | head -5

# Verify tool files are present
ls tools/compliance_local.py tools/feishu_bitable.py tools/sop_orchestrator.py tools/process_dual.py
ls skills/ | head -5

# Verify databases are present and accessible
ls shared/databases/keyword_database.db shared/databases/risk_keywords.db
```

### 2. Functionality Checks
```bash
# Test that the compliance tool still works
python tools/compliance_local.py --test

# Test that feishu tool can connect (if credentials set)
python -c "from tools.feishu_bitable import FeishuBitable; f=FeishuBitable(); print('OK' if f.test_connection() else 'FAIL')"

# Test that process_dual works (keyword processing)
echo "�测试" | python tools/process_dual.py

# Run a quick sanity check on the SOP orchestrator
python tools/sop_orchestrator.py --help 2>&1 | head -5
```

### 3. Division of Labor Verification
```bash
# Hermes should be able to modify SOP files without touching tools
# (This is a procedural check - ensure no accidental cross-edits)

# office-workbuddy should be able to modify tools without touching SOP
# (Similarly procedural)

# Verify .gitignore still excludes sensitive files
cat .gitignore | grep -E "\.env|key|secret|token"
```

### 4. Documentation Checks
- [ ] README.md reflects the unified repository and division of labor
- [ ] OPERATIONS.md contains operational procedures
- [ ] MIGRATION.md (this document) explains the migration
- [ ] AGENT_BOUNDARIES.md is still accurate and referenced

## ������ ���� ���� � ���� �� �� ↩�������� Rollback Procedure

If critical issues are discovered post-migration that require reverting to the pre-merge state:

### 1. Using the Backup Bundle
office-workbuddy provided a backup bundle: `merge_backup/opc_master_before_merge.bundle`

To restore OPC-ecommerce to pre-merge state:
```bash
cd /path/to/OPC-ecommerce
git fetch . merge_backup/opc_master_before_merge.bundle:master
git checkout master
# Verify it's the pre-merge state
git log --oneline -1  # Should show commit before merge
```

### 2. Manual Restoration (if bundle unavailable)
If you need to manually revert:
1. Reset OPC-ecommerce master to the commit before the merge commit
2. Manually remove the merged tool directories (skills/, tools/, shared/databases/, etc.)
3. Restore any SOP files that may have been overwritten (should be none if merge used correct strategy)
4. Force push with authorization

### 3. Important Notes on Rollback
- Rolling back will lose any commits made after the merge
- Keyword databases will revert to their pre-merge state
- Any changes made to tools/SOP after merge will be lost
- Coordinate with both teams before rolling back
- Consider creating a new branch from pre-merge state instead of destroying master if possible

## ������ ���� ���� �� ���� �� �� ⚠�������� Known Issues and Limitations

### 1. Temporary Increase in Repository Size
- The combined repository is larger than either individual repo
- Clone time and storage requirements increase accordingly
- Mitigation: Use shallow clones (`--depth=1`) for CI/CD if full history not needed

### 2. Adjustment to Single-Repo Workflow
- Teams used to working in separate repos must adjust to single repo
- Clear communication about which directories each team owns is essential
- Consider using CODEOWNERS file to enforce review boundaries (see below)

### 3. Potential for Accidental Cross-Edits
- With everything in one repo, there's slightly higher risk of accidental edits across boundaries
- Mitigation: 
  - Strict adherence to division of labor
  - Pre-commit hooks that warn if trying to edit files outside your domain
  - Clear documentation and training

### 4. Database Locking Concerns
- Shared databases (`keyword_database.db`, `risk_keywords.db`) are now in the same repo as tools that modify them
- Ensure proper connection handling in tools to avoid locking issues
- Consider implementing read-only replicas or caching for high-read scenarios

## ������ ���� ���� �� ���� �� �� 🙋‍�♂�������� FAQ

### Q: Does this mean Hermes can now modify tools?
**A**: No. The division of labor remains strictly enforced by mutual agreement and social convention. Hermes **must not** modify anything in `tools/` or `skills/` directories. Violations should be caught in code review.

### Q: Does this mean office-workbuddy can now modify SOP?
**A**: No. office-workbuddy **must not** modify any SOP documents, agent SKILL.md files, or governance documents (README.md, OPERATIONS.md, MIGRATION.md, AGENT_BOUNDARIES.md).

### Q: How do we enforce the division of labor technically?
**A**: Currently through mutual agreement and code review. In the future, we may consider:
- Adding a CODEOWNERS file that assigns specific directories to specific teams
- Implementing pre-commit hooks that check file paths against authorized editors
- Using branch protections to restrict certain directories to certain users

### Q: What happens if we need to hotfix a tool that's blocking SOP progress?
**A**: office-workbuddy should fix the tool as quickly as possible. Hermes should not attempt to fix tools themselves, even if it seems faster. If there's a critical blockage, escalate through the established channels.

### Q: How do we handle dependencies between SOP changes and tool changes?
**A**: Changes should still be coordinated. If an SOP change requires a tool change (or vice versa):
1. Discuss the change in the relevant forum (meeting, issue, etc.)
2. Implement the tool change first (by office-workbuddy)
3. Then implement the SOP change (by Hermes)
4. Or vice versa if the dependency is reversed
5. Both changes can be in the same PR if they're small and related, but clear ownership must be maintained

### Q: Where should I look for X?
**A**: 
- SOP definitions, agent prompts, governance: Look in `docs/`, `agents/`, `config/`
- Tools, skills, scripts: Look in `tools/`, `skills/`
- Keyword databases: Look in `shared/databases/`
- Shared references, templates: Look in `references/`, `knowledge-base/`
- Event schemas, handoff docs: Look in `shared/events/`, `handoff/`

### Q: Is the master branch safe to use for production?
**A**: Yes, after the merge and verification, the master branch contains the unified, canonical state of both SOP and tools. It should be treated as the single source of truth for all OPC-ecommerce operations.

### Q: How do I contribute if I'm on the Hermes team?
**A**: 
1. Fork the repository if needed
2. Make changes only to SOP-owned directories: `docs/SOP/`, `agents/*/SKILL.md`, `config/AGENT_BOUNDARIES.md`, `README.md`, `OPERATIONS.md`, `MIGRATION.md`
3. Ensure you don't accidentally modify tool directories
4. Submit a pull request for review
5. Wait for approval from both Hermes (SOP) and office-workbuddy (tool) if your change touches boundaries

### Q: How do I contribute if I'm on the office-workbuddy team?
**A**: 
1. Fork the repository if needed
2. Make changes only to tool-owned directories: `tools/`, `skills/`, `shared/databases/`
3. Ensure you don't accidentally modify SOP directories
4. Submit a pull request for review
5. Wait for approval from both office-workbuddy (tool) and Hermes (SOP) if your change touches boundaries

---
*Last updated: 2026-08-13*
*Version: 1.0*
*Based on merge commit: [insert actual merge hash here after merge]*