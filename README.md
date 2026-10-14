# NahaTax Intelligence — BankBook Core

NahaTax is the accountant/practice product built on the existing BankBook repository.

Repository: Naha1981/bankbook

## What changed

BankBook's existing South African financial infrastructure remains in place. NahaTax adds a separate practice/compliance domain under /api/v1/nahatax.

First workflow: VAT readiness.

Client → Documents + requirements → Evidence ledger → Deterministic checks + AI work → Exceptions → Accountant review → Approval/request information → Action receipt + audit trail → SARS adapter boundary

## NahaTax foundations

- Practice and client model
- VAT engagements and obligations
- Client document requirements
- Document intake metadata
- Evidence ledger with provenance and fact-state
- Exceptions with confidence and amount-at-risk
- AI employee work queue
- Human approval decisions
- Action receipts
- Audit events
- SARS sandbox submission boundary
- Synthetic demo-data seed
- Client readiness scoring

## API

NahaTax endpoints are namespaced so the original BankBook APIs remain available.

| Endpoint | Purpose |
|---|---|
| GET /api/v1/nahatax/health | NahaTax health and SARS mode |
| POST /api/v1/nahatax/demo/seed | Create synthetic practice data |
| GET /api/v1/nahatax/overview | Practice-level readiness summary |
| GET /api/v1/nahatax/clients | Client list |
| GET /api/v1/nahatax/clients/{id} | Client and readiness |
| POST /api/v1/nahatax/clients | Create client |
| POST /api/v1/nahatax/clients/{id}/requirements | Add missing-document requirement |
| POST /api/v1/nahatax/clients/{id}/documents | Record received document |
| GET /api/v1/nahatax/clients/{id}/evidence | Evidence ledger |
| GET /api/v1/nahatax/work | AI employee work queue |
| GET /api/v1/nahatax/exceptions | Review exceptions |
| POST /api/v1/nahatax/exceptions/{id}/decision | Approve/reject/request information |
| GET /api/v1/nahatax/audit | Audit trail |
| GET /api/v1/nahatax/receipts | Action receipts |
| GET /api/v1/nahatax/employees | AI employee catalogue |
| GET /api/v1/nahatax/sars/status | SARS adapter status |
| POST /api/v1/nahatax/sars/sandbox/prepare | Prepare a non-live SARS payload |

Use the optional X-Practice-Id header to select a practice in the current MVP.

## Important boundary

The SARS adapter is sandbox-only. It cannot claim to have submitted anything to SARS. Production integration will be implemented only after the correct SARS-authorised access channel, credentials, testing and security controls are in place.

## NahaLabs architecture

This repository is the domain application. Shared NahaLabs infrastructure stays outside it:

- NahaLLM — model/provider routing
- NahaDecision — typed decisions and probabilities
- my-own-whatsapp — messaging transport boundary
- Docling-compatible ingestion — document-to-structure
- NahaLabs Evidence Layer — provenance, temporal facts and review
- Agent Workforce Runtime — persistent AI employee execution
- Jev — controlled browser execution
- SARS Adapter — controlled external submission boundary

The product moat is not the underlying model or OSS. It is the accumulated NahaTax evidence, decision, review, workflow and outcome history.

## Run locally

pip install -r requirements.txt
export DATABASE_URL="postgresql://..."
uvicorn main:app --reload

The existing BankBook personal-finance endpoints remain available.

## Roadmap

1. Practice authentication and tenant isolation
2. Real document upload/storage + SHA-256 evidence hashes
3. Docling extraction pipeline
4. NahaLLM adapter
5. VAT reconciliation engine
6. Client WhatsApp transport
7. Deadline/compliance scheduler
8. Accountant review pack
9. Accounting-platform adapters
10. SARS-authorised production adapter
