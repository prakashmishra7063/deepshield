from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import accounts
from ..audit import audit
from ..billing import usage
from ..db import get_db
from ..deps import Ctx, get_ctx, get_current_user, require_org_admin
from ..models import Invite, Membership, Organization, Plan, User, utcnow
from ..schemas import (InviteIn, InviteOut, InvitePreview, MemberOut, MemberPatch, MeOut, OrgCreateIn, OrgOut,
                       OrgPatch, PlanOut, TokenIn)
from .auth import me_out

router = APIRouter(tags=["workspaces"])


def org_out(db: Session, org: Organization, role: str) -> OrgOut:
    members = sorted(org.members, key=lambda m: m.created_at)
    invites = []
    if role in ("owner", "admin"):
        invites = db.scalars(select(Invite).where(Invite.org_id == org.id, Invite.accepted_at.is_(None),
                                                  Invite.expires_at > utcnow()).order_by(Invite.created_at)).all()
    return OrgOut(id=org.id, name=org.name, kind=org.kind, status=org.status, my_role=role,
                  plan=PlanOut.model_validate(org.plan), usage=usage(db, org).to_dict(),
                  seats_used=accounts.seats_used(db, org),
                  members=[MemberOut(user_id=m.user_id, email=m.user.email, role=m.role, joined_at=m.created_at)
                           for m in members],
                  invites=[InviteOut.model_validate(i) for i in invites])


@router.get("/plans", response_model=list[PlanOut])
def public_plans(db: Session = Depends(get_db)):
    return db.scalars(select(Plan).where(Plan.public.is_(True)).order_by(Plan.sort)).all()


@router.get("/org", response_model=OrgOut)
def current_org(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    return org_out(db, ctx.org, ctx.role)


@router.patch("/org", response_model=OrgOut)
def rename_org(body: OrgPatch, request: Request, ctx: Ctx = Depends(require_org_admin), db: Session = Depends(get_db)):
    ctx.org.name = body.name
    audit(db, "org.rename", user_id=ctx.user.id, target=str(ctx.org.id), request=request)
    return org_out(db, ctx.org, ctx.role)


@router.post("/orgs", response_model=MeOut, status_code=201)
def create_team(body: OrgCreateIn, request: Request, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    owned = db.scalars(select(Membership).join(Organization).where(
        Membership.user_id == user.id, Membership.role == "owner", Organization.kind == "team")).all()
    if len(owned) >= 5 and user.role != "owner":
        raise HTTPException(400, "You can own at most 5 team workspaces.")
    org = Organization(name=body.name, kind="team", plan_id="free", created_by=user.id)
    db.add(org)
    db.flush()
    db.add(Membership(org_id=org.id, user_id=user.id, role="owner"))
    user.active_org_id = org.id
    db.commit()
    audit(db, "org.create", user_id=user.id, target=str(org.id), request=request)
    return me_out(db, user)


@router.post("/org/invites", response_model=InviteOut, status_code=201)
def invite(body: InviteIn, request: Request, ctx: Ctx = Depends(require_org_admin), db: Session = Depends(get_db)):
    org = ctx.org
    if org.kind == "personal":
        raise HTTPException(400, "Personal workspaces can't have other members. Create a team workspace instead.")
    if org.status != "active":
        raise HTTPException(403, "This workspace is suspended.")
    email = body.email.lower()
    if any(m.user.email == email for m in org.members):
        raise HTTPException(409, "That person is already a member.")
    if db.scalar(select(Invite).where(Invite.org_id == org.id, Invite.email == email, Invite.accepted_at.is_(None),
                                      Invite.expires_at > utcnow())):
        raise HTTPException(409, "An invitation is already pending for that email.")
    if accounts.seats_used(db, org) >= org.plan.max_members:
        raise HTTPException(402, f"The {org.plan.name} plan includes {org.plan.max_members} seat(s). "
                                 "Upgrade to invite more people.")
    inv = accounts.create_invite(db, org, ctx.user, email, body.role)
    audit(db, "org.invite", user_id=ctx.user.id, target=str(org.id), request=request, detail={"email": email})
    return inv


@router.delete("/org/invites/{invite_id}", status_code=204)
def cancel_invite(invite_id: int, ctx: Ctx = Depends(require_org_admin), db: Session = Depends(get_db)):
    inv = db.get(Invite, invite_id)
    if not inv or inv.org_id != ctx.org.id:
        raise HTTPException(404, "Invitation not found")
    db.delete(inv)
    db.commit()


@router.get("/invites/{token}", response_model=InvitePreview)
def preview_invite(token: str, db: Session = Depends(get_db)):
    inv = accounts.find_invite(db, token)
    inviter = db.get(User, inv.invited_by) if inv.invited_by else None
    return InvitePreview(org_name=inv.org.name, email=inv.email, role=inv.role,
                         inviter=inviter.email if inviter else None)


@router.post("/invites/accept", response_model=MeOut)
def accept(body: TokenIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inv = accounts.find_invite(db, body.token)
    accounts.accept_invite(db, inv, user)
    audit(db, "org.join", user_id=user.id, target=str(inv.org_id), request=request)
    return me_out(db, user)


@router.patch("/org/members/{user_id}", response_model=OrgOut)
def change_role(user_id: int, body: MemberPatch, request: Request, ctx: Ctx = Depends(require_org_admin),
                db: Session = Depends(get_db)):
    m = db.get(Membership, (ctx.org.id, user_id))
    if not m:
        raise HTTPException(404, "Member not found")
    if (body.role == "owner" or m.role == "owner") and ctx.role != "owner":
        raise HTTPException(403, "Only owners can grant or remove the owner role")
    if m.role == "owner" and body.role != "owner" and accounts.last_owner(db, ctx.org, user_id):
        raise HTTPException(409, "A workspace needs at least one owner")
    m.role = body.role
    audit(db, "org.member_role", user_id=ctx.user.id, target=str(ctx.org.id), request=request,
          detail={"member": user_id, "role": body.role})
    return org_out(db, ctx.org, ctx.role)


@router.delete("/org/members/{user_id}", status_code=204)
def remove_member(user_id: int, request: Request, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    """Admins remove members; any member may remove themselves (leave)."""
    leaving = user_id == ctx.user.id
    if not leaving and not ctx.is_admin:
        raise HTTPException(403, "Only workspace admins can remove members")
    if ctx.org.kind == "personal":
        raise HTTPException(400, "You can't leave your personal workspace")
    m = db.get(Membership, (ctx.org.id, user_id))
    if not m:
        raise HTTPException(404, "Member not found")
    if m.role == "owner" and ctx.role != "owner":
        raise HTTPException(403, "Only owners can remove an owner")
    if m.role == "owner" and accounts.last_owner(db, ctx.org, user_id):
        raise HTTPException(409, "Transfer ownership before the last owner leaves")
    db.delete(m)
    u = db.get(User, user_id)
    if u and u.active_org_id == ctx.org.id:
        u.active_org_id = None
    db.commit()
    audit(db, "org.member_removed", user_id=ctx.user.id, target=str(ctx.org.id), request=request,
          detail={"member": user_id, "left": leaving})
