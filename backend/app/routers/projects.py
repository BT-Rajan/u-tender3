from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.db import get_db
from app.deps import get_current_user, require_verified_owner
from app.models.award_record import AwardRecord
from app.models.contractor import ContractorProfile
from app.models.enums import NotificationType, OfferStatus, ProjectStatus, TenderType, UserRole
from app.models.offer import Offer
from app.models.project import Project, ProjectDrawing
from app.models.project_amendment import ProjectAmendment
from app.models.user import User
from app.schemas.amendment import ProjectAmendmentOut, ProjectAmendmentRequest
from app.schemas.award import AwardRecordOut
from app.schemas.project import DrawingOut, ProjectCreate, ProjectDetailOut
from app.services import contractor_service, tender_service
from app.services.drawings import upload_drawings_for_project
from app.services.email import notify_contractor_tender_amended
from app.services.notify import notify
from app.services.storage import drawing_url_expiry_seconds, get_storage
from app.services.tender_lifecycle import sync_expired_projects
from app.services.tender_service import TenderError, TenderFields

router = APIRouter(prefix="/projects", tags=["projects"])


# Full project detail includes signed drawing URLs — the P0 payment gate
# (spec checklist "docs approved but payment absent") applies here, not
# just verification. A verification-approved-but-unpaid contractor sees a
# 404 on this endpoint exactly like a project they're not eligible for at
# all — the response never distinguishes "doesn't exist" from "you don't
# have access yet", so it can't be used to enumerate projects. The
# lightweight /contractor/feed listing (title, deadline, offer count — no
# drawings) stays available on verification alone; that split is what lets
# an unpaid contractor browse before paying instead of a hard app lockout.
def _can_view_project(user: User, project: Project, db: Session) -> bool:
    # Delegates to the shared contractor service, so the web and WhatsApp use one visibility rule.
    return contractor_service.can_view_project(db, user, project)


@router.post("", response_model=ProjectDetailOut, status_code=201)
async def create_project(
    title: str = Form(...),
    address: str = Form(...),
    description: str | None = Form(None),
    trade: str | None = Form(None),
    bid_deadline: str = Form(...),
    tender_type: str = Form("owner_visible"),
    status: str = Form("open"),
    drawings: list[UploadFile] = File(default=[]),
    user: User = Depends(require_verified_owner),
    db: Session = Depends(get_db),
):
    from datetime import datetime

    try:
        tender_type_value = TenderType(tender_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tender type.")

    # Only these two lifecycle states can be chosen at creation — every
    # other one is reached later through an explicit owner action.
    if status not in (ProjectStatus.draft.value, ProjectStatus.open.value):
        raise HTTPException(status_code=400, detail="A new project must start as draft or open.")
    status_value = ProjectStatus(status)

    deadline = datetime.fromisoformat(bid_deadline)
    if status_value == ProjectStatus.open and deadline <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="Bid deadline must be in the future.")

    project = Project(
        owner_id=user.id,
        title=title,
        address=address,
        description=description or None,
        trade=trade or None,
        bid_deadline=deadline,
        tender_type=tender_type_value,
        status=status_value,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    real_files = [f for f in drawings if f.filename]
    if real_files:
        await upload_drawings_for_project(db, get_storage(), project.id, real_files)
        db.refresh(project)

    return _serialize_detail(project, db)


@router.get("/{project_id}", response_model=ProjectDetailOut)
def get_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sync_expired_projects(db)
    project = db.get(Project, project_id)
    if not project or not _can_view_project(user, project, db):
        raise HTTPException(status_code=404, detail="Project not found.")
    return _serialize_detail(project, db)


# A published, material change to a tender (spec §2.8/§2.12, D-007) — a
# permanent numbered record, never a silent edit. changed_fields only
# lists what actually differs from before, so a no-op PATCH (same values
# resubmitted) creates no amendment row and bumps nothing.
@router.patch("/{project_id}", response_model=ProjectDetailOut)
def amend_project(
    project_id: str, payload: ProjectAmendmentRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    sync_expired_projects(db)
    try:
        project = tender_service.owner_project(db, user, project_id)
        project = tender_service.amend(
            db,
            user,
            project,
            TenderFields(
                title=payload.title,
                description=payload.description,
                trade=payload.trade,
                bid_deadline=payload.bid_deadline,
            ),
            reason=payload.reason,
            now=datetime.utcnow(),
        )
    except TenderError as error:
        raise _tender_patch_error(error)
    return _serialize_detail(project, db)


def _tender_patch_error(error: TenderError) -> HTTPException:
    # The PATCH route has always answered "not found" and "can't amend" with 400, except for not-found.
    if error.code == "not_found":
        return HTTPException(status_code=404, detail="Project not found.")
    if error.code == "not_verified":
        return HTTPException(status_code=403, detail="not_approved")
    return HTTPException(status_code=400, detail=error.message)


@router.get("/{project_id}/amendments", response_model=list[ProjectAmendmentOut])
def list_amendments(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project or not _can_view_project(user, project, db):
        raise HTTPException(status_code=404, detail="Project not found.")
    return (
        db.query(ProjectAmendment)
        .filter(ProjectAmendment.project_id == project_id)
        .order_by(ProjectAmendment.amendment_number.asc())
        .all()
    )


@router.get("/{project_id}/award", response_model=AwardRecordOut)
def get_award(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project or not _can_view_project(user, project, db):
        raise HTTPException(status_code=404, detail="Project not found.")

    record = db.query(AwardRecord).filter(AwardRecord.project_id == project_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="This project has not been awarded.")

    cp = db.get(ContractorProfile, record.contractor_id)
    return AwardRecordOut(
        id=record.id,
        project_id=record.project_id,
        offer_id=record.offer_id,
        contractor_id=record.contractor_id,
        amount=record.amount,
        project_revision=record.project_revision,
        offer_revision=record.offer_revision,
        awarded_by=record.awarded_by,
        created_at=record.created_at,
        contractor_company_name=cp.company_name if cp else None,
    )


@router.post("/{project_id}/drawings", response_model=ProjectDetailOut)
async def add_drawings(
    project_id: str,
    drawings: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found.")

    real_files = [f for f in drawings if f.filename]
    await upload_drawings_for_project(db, get_storage(), project_id, real_files)
    db.refresh(project)
    return _serialize_detail(project, db)


@router.get("/{project_id}/drawings-zip")
def download_drawings_zip(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    import io
    import zipfile

    project = db.get(Project, project_id)
    if not project or not _can_view_project(user, project, db):
        raise HTTPException(status_code=404, detail="Project not found.")

    # Only the current revision of each drawing — a superseded version
    # stays downloadable individually via its own signed URL in the
    # history endpoint, but "download everything" means the latest set.
    drawings = (
        db.query(ProjectDrawing)
        .filter(ProjectDrawing.project_id == project_id, ProjectDrawing.is_current.is_(True))
        .all()
    )
    if not drawings:
        raise HTTPException(status_code=404, detail="No drawings on this project.")

    storage = get_storage()
    buffer = io.BytesIO()
    included = 0
    with zipfile.ZipFile(buffer, "w") as zf:
        for d in drawings:
            content = storage.download("project-drawings", d.file_path)
            if content is None:
                continue
            zf.writestr(d.file_name, content)
            included += 1

    if included == 0:
        raise HTTPException(status_code=404, detail="No accessible drawings.")

    buffer.seek(0)
    safe_title = "".join(c for c in project.title if c.isalnum() or c in " _-").strip().replace(" ", "-") or "drawings"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}-drawings.zip"'},
    )


@router.get("/{project_id}/drawings/history", response_model=list[DrawingOut])
def drawing_history(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Every revision of every drawing on this project, superseded ones
    included — the append-only record spec §2.8/§67 require. Same
    visibility rule as the project itself; a superseded row's signed URL
    still works, so old drawings are never truly gone, just no longer the
    default one shown."""
    project = db.get(Project, project_id)
    if not project or not _can_view_project(user, project, db):
        raise HTTPException(status_code=404, detail="Project not found.")

    storage = get_storage()
    expiry = drawing_url_expiry_seconds(project.bid_deadline)
    rows = (
        db.query(ProjectDrawing)
        .filter(ProjectDrawing.project_id == project_id)
        .order_by(ProjectDrawing.file_name.asc(), ProjectDrawing.revision.asc())
        .all()
    )
    return [
        DrawingOut(
            id=d.id,
            file_name=d.file_name,
            uploaded_at=d.uploaded_at,
            revision=d.revision,
            is_current=d.is_current,
            url=storage.signed_url("project-drawings", d.file_path, expiry),
        )
        for d in rows
    ]


def _serialize_detail(project: Project, db: Session) -> ProjectDetailOut:
    offer_count = db.query(Offer).filter(Offer.project_id == project.id).count()
    storage = get_storage()
    expiry = drawing_url_expiry_seconds(project.bid_deadline)
    # Current revisions only — superseded ones are never lost, just not
    # part of the default view (see /drawings/history for the full trail).
    drawing_rows = (
        db.query(ProjectDrawing)
        .filter(ProjectDrawing.project_id == project.id, ProjectDrawing.is_current.is_(True))
        .all()
    )
    drawings = [
        DrawingOut(
            id=d.id,
            file_name=d.file_name,
            uploaded_at=d.uploaded_at,
            revision=d.revision,
            is_current=d.is_current,
            url=storage.signed_url("project-drawings", d.file_path, expiry),
        )
        for d in drawing_rows
    ]
    return ProjectDetailOut(
        id=project.id,
        owner_id=project.owner_id,
        title=project.title,
        address=project.address,
        description=project.description,
        trade=project.trade,
        bid_deadline=project.bid_deadline,
        status=project.status,
        tender_type=project.tender_type,
        tender_type_locked=project.tender_type_locked,
        is_suspended=project.is_suspended,
        created_at=project.created_at,
        offer_count=offer_count,
        drawings=drawings,
    )
