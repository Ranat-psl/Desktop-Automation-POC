# Desktop Automation POC — Documentation Index

## 1. Overview

The Desktop Automation POC is a Windows desktop automation solution designed to help QA engineers record manual desktop interactions and replay them as reusable automated workflows.

The project is being developed as a foundation for a future enterprise-grade desktop automation platform.

This documentation describes the current implementation, design, testing strategy, user operation, business value, limitations and future roadmap.

---

## 2. Documentation Map

| Document | Purpose |
|---|---|
| [User Manual](USER_MANUAL.md) | How to install, operate and use the tool |
| [Business Requirements](BUSINESS_REQUIREMENTS.md) | Business problem, objectives, users and requirements |
| [User Goal & Value](USER_GOAL_AND_VALUE.md) | How the tool helps QA users achieve their goals |
| [Architecture](ARCHITECTURE.md) | System architecture and major components |
| [Design Flows](DESIGN_FLOWS.md) | Major application and processing flows |
| [Playback Lifecycle](PLAYBACK_LIFECYCLE.md) | Detailed playback lifecycle |
| [Data Model](DATA_MODEL.md) | Recording and automation data structures |
| [Algorithms](ALGORITHMS.md) | Algorithms and processing logic |
| [Test Strategy](TEST_STRATEGY.md) | Testing approach and validation strategy |
| [Troubleshooting](TROUBLESHOOTING.md) | Known problems and troubleshooting guidance |
| [Status](STATUS.md) | Current implementation status |
| [Roadmap](ROADMAP.md) | Planned development phases |
| [Contributing](CONTRIBUTING.md) | Development and contribution guidelines |

---

## 3. Recommended Reading Order

### For a QA User

1. [User Manual](USER_MANUAL.md)
2. [User Goal & Value](USER_GOAL_AND_VALUE.md)
3. [Troubleshooting](TROUBLESHOOTING.md)

### For a QA Lead / Engineering Lead

1. [Business Requirements](BUSINESS_REQUIREMENTS.md)
2. [Status](STATUS.md)
3. [Architecture](ARCHITECTURE.md)
4. [Test Strategy](TEST_STRATEGY.md)
5. [Roadmap](ROADMAP.md)

### For a Developer / Automation Engineer

1. [Architecture](ARCHITECTURE.md)
2. [Design Flows](DESIGN_FLOWS.md)
3. [Data Model](DATA_MODEL.md)
4. [Playback Lifecycle](PLAYBACK_LIFECYCLE.md)
5. [Algorithms](ALGORITHMS.md)
6. [Test Strategy](TEST_STRATEGY.md)
7. [Contributing](CONTRIBUTING.md)

---

## 4. Current Project Position

The project has progressed beyond a basic recorder prototype.

The current foundation includes:

- Desktop action recording
- Recording persistence
- Playback/execution
- Keyboard actions
- Mouse click actions
- Mixed keyboard and mouse workflows
- Workspace management
- Recording lifecycle handling
- Playback lifecycle handling
- Coordinate metadata
- Coordinate scaling
- Recording format versioning
- Backward compatibility
- HTML execution reporting
- Automated regression validation

The current implementation should still be considered a **POC/MVP foundation**, not a complete enterprise production platform.

---

## 5. Documentation Principles

All project documentation follows these principles:

- Document the actual implementation.
- Do not represent planned functionality as implemented.
- Clearly identify known limitations.
- Keep architecture and implementation documentation aligned.
- Update documentation when major behavior changes.
- Maintain test results with the corresponding development baseline.

---

## 6. Project Vision

The long-term vision is to evolve the POC into a reliable desktop automation platform that enables QA teams to:

**Record → Reuse → Replay → Validate → Report → Maintain → Scale**

Future capabilities may extend this foundation toward robust application identification, test case management, automation/code generation, CI/CD execution, advanced reporting and AI-assisted automation.