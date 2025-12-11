# Backup Judges Architecture Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER REQUEST                                 │
│                    "Create a new feature"                            │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      StingyJudge                                     │
│                 async judge(prompt) → (score, impact, reasoning)    │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      JudgeRegistry                                   │
│                 judge_with_failover(prompt, max_attempts=3)         │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │              JudgeHealthTracker                             │    │
│  │            (Circuit Breaker Manager)                        │    │
│  │                                                             │    │
│  │  • Tracks failures per judge                               │    │
│  │  • Opens circuit after threshold                           │    │
│  │  • Manages cooldown periods                                │    │
│  │  • Records success/failure timestamps                      │    │
│  └────────────────────────────────────────────────────────────┘    │
└──────────┬──────────────────────┬─────────────────────────┬─────────┘
           │                      │                         │
           ▼                      ▼                         ▼
    ┌─────────────┐      ┌─────────────┐          ┌─────────────┐
    │  JudgeModel │      │  JudgeModel │          │  Fallback   │
    │  (Primary)  │      │  (Backup)   │          │  (Default)  │
    ├─────────────┤      ├─────────────┤          ├─────────────┤
    │ Priority: 0 │      │ Priority: 1 │          │ Priority: ∞ │
    │ DeepSeek    │      │ Anthropic   │          │ (0.5, LOW)  │
    │             │      │ Claude      │          │             │
    │ Fast, Cheap │      │ Reliable    │          │ Safe        │
    └─────────────┘      └─────────────┘          └─────────────┘
```

## Request Flow with Failover

### Scenario 1: Normal Operation (99% of requests)

```
REQUEST
   │
   ▼
┌──────────────────────┐
│  Select Judge        │
│  (Primary first)     │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Check Circuit       │    Circuit: 🟢 CLOSED
│  Breaker             │    Available: ✅
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Call Primary        │
│  (DeepSeek)          │
└──────┬───────────────┘
       │
       ▼ ✅ SUCCESS
┌──────────────────────┐
│  Record Success      │    Reset failures to 0
│  in HealthTracker    │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  RETURN RESULT       │
│  (score, impact)     │
└──────────────────────┘
```

### Scenario 2: Primary Fails, Backup Succeeds (~0.9%)

```
REQUEST
   │
   ▼
┌──────────────────────┐
│  Select Judge        │
│  (Primary first)     │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Check Circuit       │    Circuit: 🟢 CLOSED
│  Breaker             │    Available: ✅
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Call Primary        │
│  (DeepSeek)          │
└──────┬───────────────┘
       │
       ▼ ❌ FAILURE (Timeout/Error)
┌──────────────────────┐
│  Record Failure      │    Failures: 0 → 1
│  in HealthTracker    │    Recent: [now]
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Select Next Judge   │
│  (Backup)            │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Check Circuit       │    Circuit: 🟢 CLOSED
│  Breaker             │    Available: ✅
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Call Backup         │
│  (Anthropic)         │
└──────┬───────────────┘
       │
       ▼ ✅ SUCCESS
┌──────────────────────┐
│  Record Success      │    Reset backup failures
│  in HealthTracker    │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  RETURN RESULT       │
│  (score, impact)     │
└──────────────────────┘
```

### Scenario 3: Circuit Breaker Opens

```
REQUEST 1, 2, 3
   │ (All fail within 5 min)
   ▼
┌──────────────────────────────────┐
│  Primary Fails 3 Times           │
│  Recent failures: [t1, t2, t3]   │
└──────┬───────────────────────────┘
       │
       ▼
┌──────────────────────────────────┐
│  ⚡ CIRCUIT BREAKER OPENS         │
│  Cooldown: 60 seconds            │
│  Circuit open until: t3 + 60s    │
└──────┬───────────────────────────┘
       │
       ▼
       
REQUEST 4
   │
   ▼
┌──────────────────────┐
│  Select Judge        │
│  (Primary first)     │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Check Circuit       │    Circuit: 🔴 OPEN
│  Breaker             │    Available: ❌
└──────┬───────────────┘
       │
       ▼ ⚡ SKIP PRIMARY (Circuit open)
┌──────────────────────┐
│  Select Next Judge   │
│  (Backup directly)   │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Call Backup         │    ⏩ Faster! (no retry)
│  (Anthropic)         │
└──────┬───────────────┘
       │
       ▼ ✅ SUCCESS
┌──────────────────────┐
│  RETURN RESULT       │
│  (score, impact)     │
└──────────────────────┘

... 60 seconds pass ...

REQUEST 5
   │
   ▼
┌──────────────────────┐
│  Check Circuit       │    Circuit: 🟢 CLOSED
│  Breaker             │    (Cooldown expired)
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Try Primary Again   │    🔄 Self-healing
│  (DeepSeek)          │
└──────┬───────────────┘
       │
       ▼ ✅ SUCCESS
┌──────────────────────┐
│  Record Success      │    Failures reset to 0
│  Circuit CLOSED      │    Circuit back to normal
└──────────────────────┘
```

## Component Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                     StingyJudge                             │    │
│  │                                                             │    │
│  │  _registry: JudgeRegistry                                  │    │
│  │                                                             │    │
│  │  async judge(prompt)                                       │    │
│  │  async judge_batch(prompts)                                │    │
│  │  async get_status()                                        │    │
│  └────────────┬───────────────────────────────────────────────┘    │
│               │ uses                                                │
│               ▼                                                     │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                   JudgeRegistry                             │    │
│  │                                                             │    │
│  │  _judges: List[JudgeModel]        (sorted by priority)    │    │
│  │  health_tracker: JudgeHealthTracker                        │    │
│  │  _default_fallback: Tuple                                  │    │
│  │                                                             │    │
│  │  register_judge(judge)                                     │    │
│  │  select_judge(exclude=[])         → JudgeModel             │    │
│  │  judge_with_failover(prompt)      → (score, impact, id)   │    │
│  │  get_registry_status()            → Dict                   │    │
│  └──────────┬─────────────────────────┬──────────────────────┘    │
│             │ contains                │ uses                       │
│             ▼                         ▼                            │
│  ┌──────────────────┐      ┌──────────────────────────────────┐   │
│  │   JudgeModel     │      │    JudgeHealthTracker            │   │
│  │                  │      │                                  │   │
│  │  judge_id        │      │  _health: Dict[id, JudgeHealth] │   │
│  │  client          │      │                                  │   │
│  │  priority        │      │  record_failure(id)             │   │
│  │  system_prompt   │      │  record_success(id)             │   │
│  │  temperature     │      │  is_available(id)               │   │
│  │                  │      │  get_status(id)                 │   │
│  │  async judge()   │      └──────────┬───────────────────────┘   │
│  └──────────────────┘                 │ manages                   │
│                                        ▼                           │
│                          ┌──────────────────────────────────┐     │
│                          │      JudgeHealth                 │     │
│                          │                                  │     │
│                          │  judge_id                        │     │
│                          │  failure_count                   │     │
│                          │  last_failure                    │     │
│                          │  last_success                    │     │
│                          │  circuit_open_until              │     │
│                          │  recent_failures: List[datetime] │     │
│                          │                                  │     │
│                          │  is_circuit_open()              │     │
│                          │  get_recent_failure_count()     │     │
│                          └──────────────────────────────────┘     │
│                                                                    │
└─────────────────────────────────────────────────────────────────┘
```

## State Transitions: Circuit Breaker

```
                    ┌─────────────┐
           ┌────────┤   CLOSED    ├────────┐
           │        │  (Normal)   │        │
           │        └─────┬───────┘        │
           │              │                │
           │        SUCCESS│                │
           │              │                │
   SUCCESS │              ▼                │ 3 FAILURES
  (reset)  │        ┌─────────────┐        │ (in 5 min)
           │        │   CLOSED    │        │
           │        │ 1-2 Failures│        │
           │        └─────┬───────┘        │
           │              │                │
           │              │ 3rd FAILURE    │
           │              ▼                │
           │        ┌─────────────┐        │
           └────────┤    OPEN     ◄────────┘
                    │ (Cooldown)  │
                    └─────┬───────┘
                          │
                    60s   │ WAIT
                  expired │
                          ▼
                    ┌─────────────┐
                    │ HALF-OPEN   │
                    │ (Try once)  │
                    └─────┬───────┘
                          │
                          │
              ┌───────────┴───────────┐
              │                       │
              ▼                       ▼
        ┌─────────────┐         ┌─────────────┐
        │   SUCCESS   │         │   FAILURE   │
        │  → CLOSED   │         │  → OPEN     │
        └─────────────┘         └─────────────┘
```

## Health Status Data Structure

```
JudgeRegistry.get_registry_status() →

{
  "judges": [
    {
      "judge_id": "deepseek-judge-primary",
      "display_name": "DeepSeek Judge (Primary)",
      "priority": 0,
      "model": "deepseek-chat",
      
      // From HealthTracker
      "available": true,
      "circuit_open": false,
      "failure_count": 0,
      "recent_failures": 0,
      "last_success": "2025-01-10T10:30:15Z",
      "last_failure": null,
      "circuit_open_until": null
    },
    {
      "judge_id": "anthropic-judge-backup",
      "display_name": "Anthropic Judge (Backup)",
      "priority": 1,
      "model": "claude-3-haiku-20240307",
      
      "available": true,
      "circuit_open": false,
      "failure_count": 0,
      "recent_failures": 0,
      "last_success": "2025-01-10T10:25:00Z",
      "last_failure": null,
      "circuit_open_until": null
    }
  ]
}
```

## Logging Output Examples

### Normal Operation
```
INFO: Initializing judge registry with backup support...
INFO: ✅ Judge registry initialized: Primary=deepseek-judge-primary, Backup=anthropic-judge-backup
DEBUG: Selected judge: deepseek-judge-primary
DEBUG: Judge deepseek-judge-primary result: score=0.3, impact=LOW, reasoning=Simple task...
INFO: Judge result from deepseek-judge-primary: score=0.300, impact=LOW
DEBUG: Judge deepseek-judge-primary success, circuit reset
```

### Failover Event
```
INFO: Judge attempt 1/3: Using DeepSeek Judge (Primary) (deepseek-judge-primary)
ERROR: ❌ Judge deepseek-judge-primary failed: Connection timeout. Trying next backup...
DEBUG: Judge deepseek-judge-primary unavailable: circuit breaker open
INFO: Judge attempt 2/3: Using Anthropic Judge (Backup) (anthropic-judge-backup)
DEBUG: Selected judge: anthropic-judge-backup
INFO: ✅ Judge success with anthropic-judge-backup: score=0.300, impact=LOW
```

### Circuit Breaker Opens
```
ERROR: ❌ Judge deepseek-judge-primary failed: Service unavailable. Trying next backup...
WARNING: Circuit breaker OPEN for judge deepseek-judge-primary: 3 failures in last 5 minutes. Cooldown until 2025-01-10T10:35:30
DEBUG: Judge deepseek-judge-primary unavailable: circuit breaker open
INFO: Selected judge: anthropic-judge-backup
```

### All Judges Fail
```
ERROR: ❌ Judge deepseek-judge-primary failed: Connection timeout. Trying next backup...
ERROR: ❌ Judge anthropic-judge-backup failed: Service unavailable. Trying next backup...
ERROR: All judges failed after 2 attempts. Tried: ['deepseek-judge-primary', 'anthropic-judge-backup']. Using default fallback.
```

## Performance Characteristics

### Latency Distribution

```
Normal case (99%):     200-500ms   (Primary succeeds)
Failover (0.9%):       400-1000ms  (Primary fails, backup succeeds)
Circuit open (varies): 200-500ms   (Skip primary, use backup directly)
All fail (0.1%):       800-2000ms  (Try all judges, use default)
```

### Cost Distribution (per 1000 requests)

```
Primary judge (DeepSeek):    990 requests × $0.0001 = $0.099
Backup judge (Anthropic):      9 requests × $0.0003 = $0.003
Fallback (free):               1 request  × $0       = $0
────────────────────────────────────────────────────
Total cost per 1000 requests:                  $0.102

Cost increase from backup: 3% (negligible)
```

## Summary

```
┌─────────────────────────────────────────────────────────────┐
│                  BACKUP JUDGES SYSTEM                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Primary Judge (DeepSeek)         ──────► 99% of traffic   │
│          │                                                   │
│          │ fails                                             │
│          ▼                                                   │
│  Backup Judge (Anthropic)         ──────► 0.9% failover    │
│          │                                                   │
│          │ fails                                             │
│          ▼                                                   │
│  Default Fallback (0.5, LOW)      ──────► 0.1% both fail   │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  Circuit Breaker: Opens after 3 failures in 5 minutes       │
│  Self-Healing:    Automatic recovery after 60s cooldown     │
│  Monitoring:      Real-time health status per judge         │
└─────────────────────────────────────────────────────────────┘
```
