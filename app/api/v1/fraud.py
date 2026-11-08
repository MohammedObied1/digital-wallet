from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import AdminUser, DBSession, PageParams, SupportUser
from app.core.exceptions import NotFoundError
from app.models import FraudEvent, FraudRule
from app.schemas.fraud import FraudEventOut, FraudRuleCreate, FraudRuleOut
from app.services import audit_service

router = APIRouter(prefix="/fraud", tags=["Fraud"])


@router.get("/rules", response_model=list[FraudRuleOut])
def list_rules(db: DBSession, _: SupportUser) -> list[FraudRuleOut]:
    rules = db.scalars(select(FraudRule).order_by(FraudRule.id)).all()
    return [FraudRuleOut.model_validate(r) for r in rules]


@router.post("/rules", response_model=FraudRuleOut, status_code=201)
def create_rule(data: FraudRuleCreate, db: DBSession, admin: AdminUser) -> FraudRuleOut:
    rule = FraudRule(**data.model_dump())
    db.add(rule)
    db.flush()
    audit_service.record(db, action="fraud_rule.create", entity_type="fraud_rule", entity_id=rule.id, actor_user_id=admin.id)
    db.commit()
    db.refresh(rule)
    return FraudRuleOut.model_validate(rule)


@router.post("/rules/{rule_id}/deactivate", response_model=FraudRuleOut)
def deactivate_rule(rule_id: int, db: DBSession, admin: AdminUser) -> FraudRuleOut:
    rule = db.get(FraudRule, rule_id)
    if not rule:
        raise NotFoundError("Fraud rule not found")
    rule.is_active = False
    audit_service.record(db, action="fraud_rule.deactivate", entity_type="fraud_rule", entity_id=rule.id, actor_user_id=admin.id)
    db.commit()
    db.refresh(rule)
    return FraudRuleOut.model_validate(rule)


@router.get("/events", response_model=dict)
def list_events(db: DBSession, page: PageParams, _: SupportUser) -> dict:
    total = db.scalar(select(func.count()).select_from(FraudEvent)) or 0
    events = db.scalars(select(FraudEvent).order_by(FraudEvent.id.desc()).offset(page.offset).limit(page.size)).all()
    return page.build([FraudEventOut.model_validate(e) for e in events], total)
