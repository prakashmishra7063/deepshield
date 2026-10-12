from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import Ctx, get_ctx
from ..models import Alert, Case, CaseItem, CaseNote
from ..schemas import AlertOut, AlertPatch, CaseDetail, CaseIn, CaseItemIn, CaseOut, CasePatch, NoteIn, NoteOut
from .analyses import owned, summary

router = APIRouter(tags=["cases & alerts"])


def _case(db: Session, ctx: Ctx, case_id: int) -> Case:
    c = db.get(Case, case_id)
    if not c or c.org_id != ctx.org.id:
        raise HTTPException(404, "Case not found")
    return c


def _detail(c: Case) -> CaseDetail:
    return CaseDetail(id=c.id, title=c.title, status=c.status, created_at=c.created_at, updated_at=c.updated_at,
                      item_count=len(c.items), items=[summary(i.analysis) for i in c.items],
                      notes=[NoteOut.model_validate(n) for n in c.notes])


@router.get("/cases", response_model=list[CaseOut])
def list_cases(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(CaseItem.case_id, func.count()).join(Case).where(Case.org_id == ctx.org.id)
                             .group_by(CaseItem.case_id)).all())
    cases = db.scalars(select(Case).where(Case.org_id == ctx.org.id).order_by(Case.updated_at.desc())).all()
    return [CaseOut(id=c.id, title=c.title, status=c.status, created_at=c.created_at, updated_at=c.updated_at,
                    item_count=counts.get(c.id, 0)) for c in cases]


@router.post("/cases", response_model=CaseDetail, status_code=201)
def create_case(body: CaseIn, request: Request, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    c = Case(org_id=ctx.org.id, user_id=ctx.user.id, title=body.title)
    db.add(c)
    db.flush()
    if body.analysis_id:
        owned(db, ctx, body.analysis_id)
        db.add(CaseItem(case_id=c.id, analysis_id=body.analysis_id))
    db.commit()
    db.refresh(c)
    audit(db, "case.create", user_id=ctx.user.id, target=str(c.id), request=request)
    return _detail(c)


@router.get("/cases/{case_id}", response_model=CaseDetail)
def get_case(case_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    return _detail(_case(db, ctx, case_id))


@router.patch("/cases/{case_id}", response_model=CaseDetail)
def patch_case(case_id: int, body: CasePatch, request: Request, ctx: Ctx = Depends(get_ctx),
               db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    if body.title is not None:
        c.title = body.title
    if body.status is not None:
        c.status = body.status
    db.commit()
    audit(db, "case.update", user_id=ctx.user.id, target=str(c.id), request=request, detail=body.model_dump(exclude_none=True))
    return _detail(c)


@router.delete("/cases/{case_id}", status_code=204)
def delete_case(case_id: int, request: Request, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    db.delete(_case(db, ctx, case_id))
    db.commit()
    audit(db, "case.delete", user_id=ctx.user.id, target=str(case_id), request=request)


@router.post("/cases/{case_id}/items", response_model=CaseDetail)
def add_item(case_id: int, body: CaseItemIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    owned(db, ctx, body.analysis_id)
    if not db.get(CaseItem, (case_id, body.analysis_id)):
        db.add(CaseItem(case_id=case_id, analysis_id=body.analysis_id))
        db.commit()
        db.refresh(c)
    return _detail(c)


@router.delete("/cases/{case_id}/items/{analysis_id}", response_model=CaseDetail)
def remove_item(case_id: int, analysis_id: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    item = db.get(CaseItem, (case_id, analysis_id))
    if item:
        db.delete(item)
        db.commit()
        db.refresh(c)
    return _detail(c)


@router.post("/cases/{case_id}/notes", response_model=CaseDetail, status_code=201)
def add_note(case_id: int, body: NoteIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    db.add(CaseNote(case_id=c.id, user_id=ctx.user.id, body=body.body))
    db.commit()
    db.refresh(c)
    return _detail(c)


@router.get("/analyses/{analysis_id}/cases", response_model=list[CaseOut])
def cases_for_analysis(analysis_id: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    owned(db, ctx, analysis_id)
    cases = db.scalars(select(Case).join(CaseItem).where(CaseItem.analysis_id == analysis_id,
                                                          Case.org_id == ctx.org.id)).all()
    return [CaseOut.model_validate(c) for c in cases]


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(state: str | None = None, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    stmt = select(Alert).where(Alert.user_id == ctx.user.id)
    if state:
        stmt = stmt.where(Alert.state == state)
    return db.scalars(stmt.order_by(Alert.created_at.desc()).limit(200)).all()


@router.patch("/alerts/{alert_id}", response_model=AlertOut)
def patch_alert(alert_id: int, body: AlertPatch, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    al = db.get(Alert, alert_id)
    if not al or al.user_id != ctx.user.id:
        raise HTTPException(404, "Alert not found")
    al.state = body.state
    db.commit()
    return al

