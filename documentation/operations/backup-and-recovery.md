# Backup and Recovery

This guide covers backup strategies and disaster recovery procedures for SentinelRouter. Proper backups are essential for maintaining system state, configuration, and audit trails.

## Overview

SentinelRouter manages three types of persistent data:

1. **Configuration**: `config/models_config.json` and environment variables
2. **State**: SQLite database with sessions, routing decisions, and budget tracking
3. **Observability**: Logs and metrics files

## Backup Strategies

### 1. Configuration Backup

#### What to Backup
- `config/models_config.json` - Main configuration file
- `.env` - Environment variables (API keys, secrets)
- Docker configuration files (`Dockerfile`, `docker-compose.yml`)
- Custom scripts and migration files

#### Backup Frequency
- **Daily** for production systems
- **Before any configuration change** for ad-hoc backups
- **Version-controlled** for configuration files

#### Backup Methods

##### Manual Backup
```bash
# Create timestamped backup
BACKUP_DIR="backups/config/$(date +%Y%m%d_%H%M%S)"
mkdir -p $BACKUP_DIR
cp config/models_config.json $BACKUP_DIR/
cp .env $BACKUP_DIR/  # Be careful with secrets!
cp docker-compose.yml $BACKUP_DIR/
cp Dockerfile $BACKUP_DIR/

# Compress backup
tar -czf $BACKUP_DIR.tar.gz $BACKUP_DIR
```

##### Automated Backup (Cron Job)
```bash
# Add to crontab -e
0 2 * * * /path/to/sentinelrouter/scripts/backup_config.sh
```

##### Git-based Backup
```bash
# Version control for configuration
git add config/models_config.json
git commit -m "Backup configuration $(date)"
git push origin main
```

### 2. Database Backup

#### SQLite Backup Methods

##### Online Backup (Recommended)
```python
# Use SQLite backup API via Python script
import sqlite3
import shutil
from datetime import datetime

def backup_database(source_path: str, backup_dir: str):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{backup_dir}/sentinelrouter_{timestamp}.db"
    
    # Copy the database file (SQLite supports concurrent reads during copy)
    shutil.copy2(source_path, backup_path)
    
    # Verify backup
    conn = sqlite3.connect(backup_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM sessions")
    count = cursor.fetchone()[0]
    conn.close()
    
    print(f"Backup created: {backup_path} ({count} sessions)")
    return backup_path
```

##### SQL Dump Backup
```bash
# Export to SQL
sqlite3 data/sentinelrouter.db .dump > backup_$(date +%Y%m%d).sql

# Compress
gzip backup_$(date +%Y%m%d).sql
```

##### Docker Volume Backup
```bash
# Backup Docker volume
docker run --rm \
  -v sentinelrouter_data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/data_$(date +%Y%m%d).tar.gz -C /data .

# Restore from backup
docker run --rm \
  -v sentinelrouter_data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar xzf /backup/data_20251214.tar.gz -C /data
```

#### Backup Frequency
- **Production**: Every 4 hours for active systems
- **Development**: Daily
- **Before upgrades**: Always backup before version updates

### 3. Logs and Metrics Backup

#### What to Backup
- `logs/requests/` - JSON audit logs
- `logs/metrics/` - JSONL metrics files
- `logs/sentinelrouter.log` - Application logs

#### Retention Policy
- Keep 30 days of logs for debugging
- Keep 90 days of metrics for trend analysis
- Archive older logs to cold storage

#### Backup Script Example
```bash
#!/bin/bash
# scripts/backup_logs.sh

DATE=$(date +%Y%m%d)
BACKUP_DIR="backups/logs/$DATE"
mkdir -p $BACKUP_DIR

# Copy log files
cp -r logs/requests $BACKUP_DIR/
cp -r logs/metrics $BACKUP_DIR/
cp logs/sentinelrouter.log $BACKUP_DIR/

# Compress
tar -czf $BACKUP_DIR.tar.gz $BACKUP_DIR

# Remove old backups (keep 30 days)
find backups/logs -name "*.tar.gz" -mtime +30 -delete
```

## Recovery Procedures

### 1. Full System Recovery

#### Scenario: Complete system failure (server crash, disk failure)

**Recovery Steps:**

1. **Restore Infrastructure**
   ```bash
   # Recreate directory structure
   mkdir -p sentinelrouter/{config,data,logs,backups}
   ```

2. **Restore Configuration**
   ```bash
   # Copy backed up configuration
   tar -xzf backups/config/20251214_120000.tar.gz
   cp -r 20251214_120000/config/* config/
   cp 20251214_120000/.env .
   ```

3. **Restore Database**
   ```bash
   # Restore SQLite database
   cp backups/db/sentinelrouter_20251214.db data/sentinelrouter.db
   
   # Verify database
   sqlite3 data/sentinelrouter.db "PRAGMA integrity_check;"
   ```

4. **Restore Docker Environment**
   ```bash
   # Rebuild and start
   docker-compose down
   docker-compose build --no-cache
   docker-compose up -d
   ```

5. **Verify Recovery**
   ```bash
   # Check health endpoint
   curl http://localhost:8000/health
   
   # Check database connectivity
   docker exec sentinelrouter sqlite3 /home/sentinel/app/data/sentinelrouter.db \
     "SELECT COUNT(*) FROM sessions;"
   ```

### 2. Partial Recovery Scenarios

#### Scenario: Configuration Corruption

**Symptoms:**
- Server fails to start with configuration errors
- Invalid JSON in models_config.json
- Missing required fields

**Recovery:**
```bash
# 1. Stop the service
docker-compose stop

# 2. Restore from backup
cp backups/config/latest/models_config.json config/

# 3. Validate configuration
python -c "
import json
with open('config/models_config.json') as f:
    data = json.load(f)
print('Configuration valid')
"

# 4. Restart
docker-compose up -d
```

#### Scenario: Database Corruption

**Symptoms:**
- "Database disk image is malformed" errors
- Queries return inconsistent results
- SQLite operational errors

**Recovery:**
```bash
# 1. Stop the service
docker-compose stop

# 2. Backup corrupted database (for analysis)
cp data/sentinelrouter.db data/sentinelrouter.db.corrupted

# 3. Restore from backup
cp backups/db/sentinelrouter_20251214.db data/sentinelrouter.db

# 4. Run integrity check
sqlite3 data/sentinelrouter.db "PRAGMA integrity_check;"

# 5. Restart
docker-compose up -d
```

#### Scenario: Lost API Keys

**Symptoms:**
- 401 Unauthorized errors from LLM providers
- Judge fails consistently
- "API key missing" in logs

**Recovery:**
```bash
# 1. Update .env file with correct API keys
echo "DEEPSEEK_API_KEY=your_new_key" >> .env
echo "ANTHROPIC_API_KEY=your_new_key" >> .env
echo "GEMINI_API_KEY=your_new_key" >> .env

# 2. Restart services
docker-compose restart

# 3. Test API keys
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Test"}], "session_id": "recovery_test"}'
```

### 3. State Recovery

#### Recovering Session State

If the database is restored but runtime state (in-memory) is lost:

1. **Reinitialize StateManager**
   ```python
   # The StateManager will reload from configuration and database
   from sentinelrouter.state_manager import StateManager
   state_manager = StateManager()
   await state_manager.initialize()
   ```

2. **Rebuild Model Registry**
   ```python
   # Model registry will be rebuilt on startup
   # Verify all models are active
   from sentinelrouter.model_registry import ModelRegistry
   registry = ModelRegistry()
   status = registry.get_registry_status()
   print(status)
   ```

3. **Reset Circuit Breakers**
   ```python
   # Circuit breakers will reset on startup
   # Check provider health
   from sentinelrouter.model_registry import ProviderHealthTracker
   tracker = ProviderHealthTracker()
   print(tracker.get_status("gemini-primary"))
   ```

## Disaster Recovery Plan

### RTO (Recovery Time Objective)
- **Configuration**: 15 minutes
- **Database**: 30 minutes
- **Full System**: 60 minutes

### RPO (Recovery Point Objective)
- **Configuration**: 24 hours
- **Database**: 4 hours
- **Logs**: 1 hour

### Recovery Team Roles
- **Primary**: System Administrator - Full recovery authority
- **Secondary**: DevOps Engineer - Database and configuration recovery
- **Tertiary**: Developer - Application-specific recovery

### Communication Plan
1. **Detection**: Automated alerts via monitoring system
2. **Notification**: Slack/Email to recovery team
3. **Status Updates**: Every 15 minutes during recovery
4. **Post-Mortem**: Within 24 hours of resolution

## Testing Backups

### Regular Backup Validation

#### Weekly Test Procedure
```bash
# 1. Create test environment
mkdir -p test_recovery
cd test_recovery

# 2. Restore latest backup
tar -xzf ../backups/full/latest.tar.gz

# 3. Start test instance
docker-compose -f docker-compose.test.yml up -d

# 4. Run validation tests
python ../scripts/validate_recovery.py

# 5. Clean up
docker-compose -f docker-compose.test.yml down
cd ..
rm -rf test_recovery
```

#### Validation Checklist
- [ ] Configuration files are valid JSON/YAML
- [ ] Database integrity check passes
- [ ] All API keys are present and valid
- [ ] Services start without errors
- [ ] Health endpoints respond 200 OK
- [ ] Basic routing functionality works
- [ ] Historical data is accessible

### Automated Recovery Testing

Create a CI/CD pipeline that:
1. Takes a backup of staging environment
2. Simulates failure (corrupts database, removes config)
3. Executes recovery scripts
4. Validates system functionality
5. Reports success/failure

## Backup Storage Considerations

### Storage Locations
- **Local**: Fast access, vulnerable to hardware failure
- **Network Storage (NAS)**: Shared access, better redundancy
- **Cloud Storage (S3, GCS)**: High durability, geographic distribution
- **Tape/Archive**: Long-term retention, cold storage

### Encryption
```bash
# Encrypt sensitive backups
gpg --symmetric --cipher-algo AES256 backup.tar.gz
# Enter passphrase when prompted

# Decrypt for recovery
gpg --output backup.tar.gz --decrypt backup.tar.gz.gpg
```

### Retention Schedule
| Backup Type | Retention | Storage Location |
|-------------|-----------|------------------|
| Configuration | 90 days | Cloud Storage |
| Database | 30 days | Network Storage |
| Logs | 7 days | Local Disk |
| Metrics | 90 days | Cloud Storage |
| Full System | 1 year | Archive Storage |

## Migration Scenarios

### 1. Migrating to New Server

**Procedure:**
```bash
# Source server
./scripts/backup_full.sh
scp backup_full.tar.gz user@newserver:/backups/

# Destination server
tar -xzf backup_full.tar.gz
cd sentinelrouter
docker-compose up -d
```

### 2. Upgrading SentinelRouter Version

**Pre-upgrade Checklist:**
- [ ] Full system backup completed
- [ ] Database backup verified
- [ ] Configuration backed up
- [ ] Downtime window scheduled

**Rollback Procedure:**
```bash
# If upgrade fails
docker-compose down
git checkout previous_version_tag
cp -r backups/config/* config/
cp backups/db/sentinelrouter.db data/
docker-compose up -d
```

### 3. Database Migration (SQLite to PostgreSQL)

**Preparation:**
```bash
# Backup SQLite database
sqlite3 data/sentinelrouter.db .dump > migration.sql

# Convert for PostgreSQL
sed -i 's/INTEGER PRIMARY KEY/SERIAL PRIMARY KEY/g' migration.sql
sed -i 's/DATETIME/TIMESTAMP/g' migration.sql

# Import to PostgreSQL
psql -h localhost -U sentinelrouter -d sentinelrouter -f migration.sql

# Update configuration
echo "DATABASE_URL=postgresql://user:pass@localhost/sentinelrouter" >> .env
```

## Monitoring Backup Health

### Key Metrics to Monitor
- **Backup Success Rate**: Percentage of successful backups
- **Backup Size**: Trend analysis to detect anomalies
- **Backup Duration**: Time to complete backups
- **Storage Usage**: Available space in backup storage
- **Recovery Test Success**: Regular test results

### Alerting Rules
- Backup fails for 2 consecutive attempts
- Backup size drops by >50% (possible failure)
- Storage usage >90%
- Recovery test fails

### Dashboard Integration
Add backup health to the SentinelRouter dashboard:
```python
@app.get("/api/backup-health")
async def backup_health():
    return {
        "last_backup": last_backup_time,
        "backup_size": backup_size_mb,
        "success_rate": success_rate_percent,
        "storage_available": storage_available_gb
    }
```

## Conclusion

A robust backup and recovery strategy is essential for maintaining SentinelRouter's reliability. Key principles:

1. **Automate Everything**: Manual backups are error-prone
2. **Test Regularly**: Untested backups are worse than no backups
3. **Follow 3-2-1 Rule**: 3 copies, 2 different media, 1 offsite
4. **Document Procedures**: Clear steps for team members
5. **Monitor Health**: Proactive detection of backup issues

Regularly review and update this plan as the system evolves and new requirements emerge.